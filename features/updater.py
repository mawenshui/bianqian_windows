# -*- coding: utf-8 -*-
"""
自动更新模块

负责检测 GitHub Release 最新版本、下载更新包、以及调度替换重启流程。
包含以下组件：
- UpdateChecker(QThread): 后台查询最新版本
- UpdateDownloader(QThread): 后台下载更新文件（主链接+备用镜像）
- UpdateDialog(QDialog): 更新内容展示与确认对话框
- UpdateProgressDialog(QDialog): 下载进度对话框
- 安装类型检测与辅助脚本生成
"""
import os
import sys
import json
import re
import tempfile
import subprocess
import urllib.request
import urllib.error
import socket

from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QProgressBar
)

from core import get_project_root

# ==================== 常量 ====================

GITHUB_REPO = 'mawenshui/bianqian_windows'
# 版本检查端点列表（按优先级排序，依次尝试）
VERSION_CHECK_ENDPOINTS = [
    ('GitHub API', f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'),
    ('GitHub 镜像', f'https://ghfast.top/https://api.github.com/repos/{GITHUB_REPO}/releases/latest'),
]

# 下载超时（秒）
GITHUB_DOWNLOAD_TIMEOUT = 60       # GitHub 主链接
MIRROR_DOWNLOAD_TIMEOUT = 120      # 镜像备用链接（较慢）
VERSION_CHECK_TIMEOUT = 30         # 版本检查请求（国内网络较慢，延长至30秒）

DOWNLOAD_CHUNK_SIZE = 128 * 1024   # 128KB

# 国内加速镜像（ghproxy.com）
MIRROR_PREFIX = 'https://ghproxy.com/'


# ==================== 工具函数 ====================

def parse_version(version_str):
    """
    解析版本号字符串为可比较的元组。
    
    支持 "1.3.1" 和 "v1.3.1" 两种格式。
    非法输入返回 (0, 0, 0)。
    """
    if not version_str:
        return (0, 0, 0)
    try:
        clean = version_str.lstrip('v').strip()
        parts = clean.split('.')
        result = []
        for p in parts[:3]:
            result.append(int(re.sub(r'[^0-9]', '', p) or '0'))
        while len(result) < 3:
            result.append(0)
        return tuple(result[:3])
    except Exception:
        return (0, 0, 0)


def detect_install_type():
    """
    检测当前安装类型。
    
    Returns:
        'msi'      — 通过 MSI 安装（路径含 Program Files\\StickyNote）
        'portable' — 便携版（frozen 但不在 Program Files）
        'source'   — 源码运行（开发模式）
    """
    if not getattr(sys, 'frozen', False):
        return 'source'
    exe_path = os.path.normpath(sys.executable).lower()
    # 匹配 "Program Files\StickyNote" 或 "Program Files (x86)\StickyNote"
    if re.search(r'program files(?: \(x86\))?\\stickynote', exe_path):
        return 'msi'
    return 'portable'


def get_download_urls(original_url):
    """
    生成下载 URL 列表（主链接 + 备用镜像）。
    
    Args:
        original_url: GitHub 资产的 browser_download_url
    
    Returns:
        [(url, timeout_seconds), ...] 优先级从高到低
    """
    urls = [
        (original_url, GITHUB_DOWNLOAD_TIMEOUT),
    ]
    # 国内加速镜像
    if MIRROR_PREFIX:
        urls.append((MIRROR_PREFIX + original_url, MIRROR_DOWNLOAD_TIMEOUT))
    return urls


# ==================== UpdateChecker ====================

class UpdateChecker(QThread):
    """后台查询 GitHub 最新 Release 版本"""
    
    status_update = pyqtSignal(str)   # 状态消息（用于进度展示）
    update_available = pyqtSignal(dict)
    no_update = pyqtSignal()
    check_failed = pyqtSignal(str)
    
    def __init__(self, current_version, timeout=None):
        super().__init__()
        self._current_version = current_version
        self._timeout = timeout or VERSION_CHECK_TIMEOUT
        self._aborted = False
    
    def abort(self):
        """取消检查（设置标志，线程会在下次检查时退出）"""
        self._aborted = True
    
    def run(self):
        """依次尝试多个端点检查更新，任一成功即返回"""
        last_error = ''
        for endpoint_name, endpoint_url in VERSION_CHECK_ENDPOINTS:
            if self._aborted:
                self.check_failed.emit('检查已取消')
                return
            try:
                self.status_update.emit(f'正在通过 {endpoint_name} 检查更新...')
                req = urllib.request.Request(
                    endpoint_url,
                    headers={'Accept': 'application/vnd.github+json'}
                )
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    if self._aborted:
                        self.check_failed.emit('检查已取消')
                        return
                    self.status_update.emit('正在解析版本信息...')
                    data = json.loads(resp.read().decode())
                
                if self._aborted:
                    self.check_failed.emit('检查已取消')
                    return
                
                tag_name = data.get('tag_name', '')
                latest_version = parse_version(tag_name)
                current_version = parse_version(self._current_version)
                
                if latest_version > current_version:
                    self.update_available.emit({
                        'version': '.'.join(map(str, latest_version)),
                        'tag': tag_name,
                        'body': data.get('body', ''),
                        'html_url': data.get('html_url', ''),
                        'assets': data.get('assets', []),
                    })
                else:
                    self.no_update.emit()
                return  # 成功，直接返回
                
            except (urllib.error.URLError, socket.timeout) as e:
                last_error = f'{endpoint_name} 连接失败: {e}'
                continue  # 尝试下一个端点
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    last_error = f'{endpoint_name} API 请求受限 (403)'
                else:
                    last_error = f'{endpoint_name} 服务器错误 (HTTP {e.code})'
                continue
            except json.JSONDecodeError:
                last_error = f'{endpoint_name} 返回数据格式异常'
                continue
            except Exception as e:
                if self._aborted:
                    self.check_failed.emit('检查已取消')
                    return
                last_error = f'{endpoint_name} 未知错误: {e}'
                continue
        
        # 所有端点都失败
        if self._aborted:
            self.check_failed.emit('检查已取消')
        else:
            self.check_failed.emit(f'所有检查端点均失败: {last_error}')


# ==================== UpdateDownloader ====================

class UpdateDownloader(QThread):
    """后台下载更新文件，内置主/备双链路"""
    
    progress = pyqtSignal(int)
    download_finished = pyqtSignal(str)
    download_failed = pyqtSignal(str)
    
    def __init__(self, download_url, asset_name):
        super().__init__()
        self._download_url = download_url
        self._asset_name = asset_name
        self._aborted = False
    
    def abort(self):
        """取消下载"""
        self._aborted = True
    
    def run(self):
        urls = get_download_urls(self._download_url)
        last_error = ''
        
        for url, timeout in urls:
            if self._aborted:
                return
            try:
                result = self._try_download(url, timeout)
                if result:
                    self.download_finished.emit(result)
                    return
            except Exception as e:
                last_error = str(e)
                continue
        
        self.download_failed.emit(
            f'所有下载源均不可用。\n\n'
            f'原始链接: {self._download_url}\n'
            f'错误信息: {last_error}\n\n'
            f'请检查网络连接或前往 GitHub Releases 手动下载。'
        )
    
    def _try_download(self, url, timeout):
        """尝试从单个 URL 下载"""
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                total_size = int(resp.headers.get('Content-Length', 0))
                downloaded = 0
                chunks = []
                
                while True:
                    if self._aborted:
                        return None
                    chunk = resp.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = int(downloaded * 100 / total_size)
                        self.progress.emit(pct)
                
                # 写入临时文件
                temp_dir = tempfile.mkdtemp(prefix='stickynote_update_')
                temp_path = os.path.join(temp_dir, self._asset_name)
                with open(temp_path, 'wb') as f:
                    for chunk in chunks:
                        f.write(chunk)
                
                return temp_path
                
        except Exception as e:
            raise  # 抛给父调用者处理


# ==================== UpdateDialog ====================

class UpdateDialog(QDialog):
    """更新内容展示与确认对话框"""
    
    def __init__(self, update_info, current_version, parent=None):
        super().__init__(parent)
        self._update_info = update_info
        self._current_version = current_version
        self._action = 'later'  # 默认稍后提醒
        self._init_ui()
    
    def _init_ui(self):
        self.setWindowTitle('发现新版本')
        self.setFixedSize(480, 430)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # 标题
        title_label = QLabel(
            f'<h2>🎉 新版本可用</h2>'
            f'<p>当前版本: <b>v{self._current_version}</b>  →  最新版本: <b>v{self._update_info["version"]}</b></p>'
        )
        title_label.setTextFormat(Qt.RichText)
        layout.addWidget(title_label)
        
        # 更新日志
        layout.addWidget(QLabel('<b>更新内容:</b>'))
        changelog = QTextEdit()
        changelog.setReadOnly(True)
        body = self._update_info.get('body', '无详细信息')
        changelog.setPlainText(body)
        layout.addWidget(changelog)
        
        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        later_btn = QPushButton('稍后提醒')
        later_btn.clicked.connect(self._on_later)
        btn_layout.addWidget(later_btn)
        
        skip_btn = QPushButton('跳过此版本')
        skip_btn.setStyleSheet('color: #888;')
        skip_btn.clicked.connect(self._on_skip)
        btn_layout.addWidget(skip_btn)
        
        btn_layout.addStretch()
        
        update_btn = QPushButton('立即更新')
        update_btn.setStyleSheet(
            'QPushButton { padding: 8px 24px; font-weight: bold; '
            'background-color: #4a86e8; color: white; border-radius: 4px; }'
            'QPushButton:hover { background-color: #3a76d8; }'
        )
        update_btn.clicked.connect(self._on_update)
        btn_layout.addWidget(update_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _on_later(self):
        self._action = 'later'
        self.accept()
    
    def _on_skip(self):
        self._action = 'skip'
        self.accept()
    
    def _on_update(self):
        self._action = 'update'
        self.accept()
    
    @property
    def action(self):
        return self._action


# ==================== UpdateProgressDialog ====================

class UpdateProgressDialog(QDialog):
    """下载进度对话框"""
    
    cancelled = pyqtSignal()
    
    def __init__(self, total_size_mb=0, parent=None):
        super().__init__(parent)
        self._cancelled = False
        self._init_ui(total_size_mb)
    
    def _init_ui(self, total_size_mb):
        self.setWindowTitle('正在下载更新...')
        self.setFixedSize(400, 150)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        self._status_label = QLabel('正在连接 GitHub...')
        layout.addWidget(self._status_label)
        
        self._progress_bar = QProgressBar()
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton('取消下载')
        cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
    
    def set_progress(self, percent):
        self._progress_bar.setValue(percent)
        size_text = f'{percent}%' if percent > 0 else '正在连接...'
        self._status_label.setText(f'下载进度: {size_text}')
    
    def set_status(self, text):
        self._status_label.setText(text)
    
    def _on_cancel(self):
        self._cancelled = True
        self.set_status('已取消下载')
        self.cancelled.emit()
        self.reject()
    
    @property
    def is_cancelled(self):
        return self._cancelled


# ==================== 安装辅助 ====================

def generate_bat_script(pid, zip_path, exe_dir, install_type, msi_path=None):
    """
    生成 .bat 更新辅助批处理脚本。
    
    执行流程:
    1. 写入日志头到 %TEMP%\\stickynote_update.log
    2. 轮询等待 PID 退出（每 1 秒检查，最多 60 秒）
    3. 使用 PowerShell Expand-Archive 解压 ZIP 到临时目录
    4. robocopy 复制文件到目标目录（重试 3 次，间隔 5 秒）
    5. MSI 用户：调用 msiexec /i 更新注册表
    6. 清理临时文件
    7. 重启 StickyNote.exe
    8. 显示日志并等待 10 秒后自动关闭
    """
    # 构建 robocopy 排除参数
    robocopy_excludes = '/XD notes backups templates /XF settings.json tags.json window_positions.json'

    msi_block = ''
    msi_cleanup = ''
    if install_type == 'msi' and msi_path:
        # MSI 路径中的反斜杠需要转义
        msi_escaped = msi_path.replace('\\', '\\\\')
        msi_block = f'''
:: ===== Step 5: Update MSI registration =====
echo [%date% %time%] Updating MSI registration via msiexec... >> "%LOGFILE%"
msiexec /i "{msi_path}" /quiet /norestart >> "%LOGFILE%" 2>&1
echo [%date% %time%] MSI registration update exit code: %ERRORLEVEL% >> "%LOGFILE%"
'''
        msi_cleanup = f'del /q "{msi_path}" 2>nul\n'

    bat_content = f'''@echo off
setlocal enabledelayedexpansion

set LOGFILE=%TEMP%\\stickynote_update.log
echo [%date% %time%] === StickyNote Update v1.5.2 === > "%LOGFILE%"
echo [%date% %time%] PID={pid} TARGET={exe_dir} TYPE={install_type} >> "%LOGFILE%"

:: ===== Step 1: Wait for main process to exit =====
echo [%date% %time%] Waiting for process PID {pid} to exit... >> "%LOGFILE%"
set WAIT_COUNT=0
:waitloop
timeout /t 1 /nobreak >nul
tasklist /fi "PID eq {pid}" 2>nul | find /i "{pid}" >nul
if errorlevel 1 goto :process_exited
set /a WAIT_COUNT+=1
if %WAIT_COUNT% LSS 60 goto :waitloop
echo [%date% %time%] WARNING: Process did not exit within 60s, proceeding anyway >> "%LOGFILE%"

:process_exited
echo [%date% %time%] Main process exited (or timeout). >> "%LOGFILE%"

:: ===== Step 2: Extract ZIP =====
set EXTRACT_DIR=%TEMP%\\stickynote_extract_%RANDOM%
mkdir "%EXTRACT_DIR%" 2>nul
echo [%date% %time%] Extracting ZIP... >> "%LOGFILE%"
powershell -NoProfile -Command "Expand-Archive -Path '{zip_path}' -DestinationPath '%EXTRACT_DIR%' -Force" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: Failed to extract ZIP >> "%LOGFILE%"
    goto :error
)
echo [%date% %time%] ZIP extraction complete. >> "%LOGFILE%"

:: ===== Step 3: Find extracted source directory =====
:: 优先检测扁平结构（StickyNote.exe 直接在解压目录下）
set SRC_DIR=%EXTRACT_DIR%
if exist "%EXTRACT_DIR%\\StickyNote.exe" goto :found_src
:: 否则查找子目录中的 StickyNote.exe（兼容带根文件夹的 ZIP）
for /d %%d in ("%EXTRACT_DIR%\\*") do (
    if exist "%%d\\StickyNote.exe" (
        set SRC_DIR=%%d
        goto :found_src
    )
)
:found_src
echo [%date% %time%] Source directory: %SRC_DIR% >> "%LOGFILE%"

:: ===== Step 4: robocopy with retry =====
echo [%date% %time%] Copying files with robocopy (retries:3, wait:5s)... >> "%LOGFILE%"
robocopy "%SRC_DIR%" "{exe_dir}" /E /R:3 /W:5 /NP /NDL {robocopy_excludes} >> "%LOGFILE%" 2>&1
set ROBO_EXIT=%ERRORLEVEL%
if %ROBO_EXIT% GEQ 8 (
    echo [%date% %time%] ERROR: robocopy failed with exit code %ROBO_EXIT% >> "%LOGFILE%"
    goto :error
)
echo [%date% %time%] File copy complete (robocopy exit: %ROBO_EXIT%). >> "%LOGFILE%"
{msi_block}
:: ===== Step 6: Cleanup =====
echo [%date% %time%] Cleaning up temporary files... >> "%LOGFILE%"
rmdir /s /q "%EXTRACT_DIR%" 2>nul
del /q "{zip_path}" 2>nul
{msi_cleanup}
:: ===== Step 7: Restart application =====
echo [%date% %time%] Starting new version... >> "%LOGFILE%"
start "" "{exe_dir}\\StickyNote.exe"
echo [%date% %time%] === Update completed successfully === >> "%LOGFILE%"

:: ===== Step 8: Show result =====
echo.
echo ============================================
echo   StickyNote update completed successfully!
echo   Log file: %LOGFILE%
echo ============================================
echo.
echo This window will close in 10 seconds...
timeout /t 10 /nobreak >nul
exit /b 0

:error
echo [%date% %time%] === Update FAILED === >> "%LOGFILE%"
echo.
echo ============================================
echo   UPDATE FAILED!
echo   See log: %LOGFILE%
echo ============================================
echo.
pause
exit /b 1
'''
    return bat_content


def execute_update(manager, zip_file_path, install_type, msi_path=None):
    """
    执行更新流程最后一步：保存窗口位置 → 生成 .bat 脚本 → 启动脚本并退出应用。
    
    Args:
        manager: 主窗口 Manager 实例
        zip_file_path: 下载的 portable ZIP 文件路径
        install_type: 安装类型 ('msi' | 'portable' | 'source')
        msi_path: MSI 文件路径（仅 MSI 用户需要，用于更新注册表）
    """
    # 保存窗口位置
    if hasattr(manager, 'save_window_positions'):
        try:
            manager.save_window_positions()
        except Exception:
            pass

    # 获取当前进程 PID
    pid = os.getpid()

    # 确定目标 exe 目录
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
    else:
        # 开发模式：使用项目根目录下的 dist/StickyNote（如果存在）
        exe_dir = os.path.join(get_project_root(), 'dist', 'StickyNote')
        if not os.path.isdir(exe_dir):
            exe_dir = os.path.dirname(sys.executable)

    # 生成 .bat 脚本
    bat_script = generate_bat_script(pid, zip_file_path, exe_dir, install_type, msi_path)
    bat_path = os.path.join(tempfile.gettempdir(), 'stickynote_update.bat')
    with open(bat_path, 'w', encoding='utf-8') as f:
        f.write(bat_script)

    # 启动 .bat（CREATE_NEW_CONSOLE 使控制台可见，用户能看到进度）
    try:
        subprocess.Popen(
            ['cmd.exe', '/c', bat_path],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    except Exception as e:
        print(f'[更新] 无法启动更新脚本: {e}')

    # 退出应用
    from PyQt5.QtWidgets import QApplication
    QApplication.instance().quit()

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
CONNECTION_TEST_TIMEOUT = 8        # 连接测试超时（秒）

DOWNLOAD_CHUNK_SIZE = 128 * 1024   # 128KB

# 下载源列表（按优先级排序，依次尝试）
# 每个源: (名称, URL前缀, 超时秒数)
# 特殊前缀 '{url}' 表示直接使用原始URL（GitHub官方）
DOWNLOAD_SOURCES = [
    ('GitHub 官方源', '{url}', GITHUB_DOWNLOAD_TIMEOUT),
    ('ghfast.top 镜像', 'https://ghfast.top/{url}', MIRROR_DOWNLOAD_TIMEOUT),
    ('ghproxy.net 镜像', 'https://ghproxy.net/{url}', MIRROR_DOWNLOAD_TIMEOUT),
    ('gh-proxy.com 镜像', 'https://gh-proxy.com/{url}', MIRROR_DOWNLOAD_TIMEOUT),
]


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
    生成下载 URL 列表（官方源 + 多个国内镜像）。
    
    Args:
        original_url: GitHub 资产的 browser_download_url
    
    Returns:
        [(source_name, url, timeout_seconds), ...] 优先级从高到低
    """
    urls = []
    for name, prefix, timeout in DOWNLOAD_SOURCES:
        if prefix == '{url}':
            url = original_url
        else:
            url = prefix.replace('{url}', original_url)
        urls.append((name, url, timeout))
    return urls


def test_connection(url, timeout=CONNECTION_TEST_TIMEOUT):
    """
    测试 URL 连通性（发送 HEAD 请求或小型 GET 请求）。
    
    Args:
        url: 待测试的 URL
        timeout: 超时秒数
    
    Returns:
        (success: bool, error_msg: str)
    """
    try:
        req = urllib.request.Request(url, method='HEAD')
        req.add_header('User-Agent', 'StickyNote-Updater')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if 200 <= code < 400:
                return (True, '')
            return (False, f'HTTP {code}')
    except urllib.error.HTTPError as e:
        # HEAD 不支持时尝试 GET（Range 只取前 1KB）
        if e.code == 405 or e.code == 403:
            try:
                req2 = urllib.request.Request(url)
                req2.add_header('Range', 'bytes=0-1023')
                req2.add_header('User-Agent', 'StickyNote-Updater')
                with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                    return (True, '')
            except Exception as e2:
                return (False, _format_error(e2))
        return (False, f'HTTP {e.code}: {e.reason}')
    except Exception as e:
        return (False, _format_error(e))


def _format_error(e):
    """将异常格式化为可读的错误描述"""
    if isinstance(e, socket.timeout):
        return '连接超时'
    elif isinstance(e, urllib.error.URLError):
        reason = str(e.reason)
        if 'timed out' in reason.lower():
            return '连接超时'
        elif 'Name or service not known' in reason or 'getaddrinfo' in reason:
            return 'DNS 解析失败'
        elif 'Connection refused' in reason:
            return '连接被拒绝'
        elif 'No route to host' in reason:
            return '无法路由到目标主机'
        return f'网络错误: {reason}'
    elif isinstance(e, ConnectionError):
        return f'连接错误: {e}'
    return str(e)


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
    """后台下载更新文件，支持多源自动切换、连接测试、自动重试"""
    
    progress = pyqtSignal(int)
    download_finished = pyqtSignal(str)
    download_failed = pyqtSignal(str)
    status_update = pyqtSignal(str)     # 状态消息（当前源、连接测试等）
    source_changed = pyqtSignal(str)    # 当前使用的下载源名称
    
    def __init__(self, download_url, asset_name):
        super().__init__()
        self._download_url = download_url
        self._asset_name = asset_name
        self._aborted = False
    
    def abort(self):
        """取消下载"""
        self._aborted = True
    
    def run(self):
        sources = get_download_urls(self._download_url)
        errors = []  # 收集每个源的失败原因
        
        # 阶段 1: 连接测试，找到第一个可用的源
        self.status_update.emit('正在测试下载源连通性...')
        available_sources = []
        
        for source_name, url, timeout in sources:
            if self._aborted:
                return
            self.status_update.emit(f'正在测试 {source_name}...')
            ok, err_msg = test_connection(url, CONNECTION_TEST_TIMEOUT)
            if ok:
                available_sources.append((source_name, url, timeout))
                self.status_update.emit(f'{source_name} ✓ 可用')
                break  # 找到第一个可用的就开始下载
            else:
                errors.append((source_name, err_msg))
                self.status_update.emit(f'{source_name} ✗ {err_msg}')
        
        if not available_sources:
            # 所有源都不可用，但仍尝试第一个源（连接测试可能误判）
            self.status_update.emit('连接测试均失败，尝试直接下载...')
            available_sources = [(sources[0][0], sources[0][1], sources[0][2])]
        
        # 阶段 2: 依次尝试可用源下载
        for source_name, url, timeout in available_sources:
            if self._aborted:
                return
            
            self.source_changed.emit(source_name)
            self.status_update.emit(f'正在通过 {source_name} 下载...')
            self.status_update.emit(f'URL: {url[:80]}...' if len(url) > 80 else f'URL: {url}')
            
            try:
                result = self._try_download(url, timeout, source_name)
                if result:
                    self.download_finished.emit(result)
                    return
            except Exception as e:
                err_detail = _format_error(e)
                errors.append((source_name, err_detail))
                self.status_update.emit(f'{source_name} 下载失败: {err_detail}')
                continue
        
        # 所有源都失败，尝试剩余未测试的源
        tested_names = {s[0] for s in available_sources}
        for source_name, url, timeout in sources:
            if source_name in tested_names or self._aborted:
                continue
            self.source_changed.emit(source_name)
            self.status_update.emit(f'正在尝试备用源 {source_name}...')
            try:
                result = self._try_download(url, timeout, source_name)
                if result:
                    self.download_finished.emit(result)
                    return
            except Exception as e:
                errors.append((source_name, _format_error(e)))
                continue
        
        # 全部失败，生成详细错误报告
        self._emit_failure(errors)
    
    def _try_download(self, url, timeout, source_name=''):
        """尝试从单个 URL 下载"""
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'StickyNote-Updater')
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
            
            if not chunks:
                raise Exception('下载内容为空')
            
            # 写入临时文件
            temp_dir = tempfile.mkdtemp(prefix='stickynote_update_')
            temp_path = os.path.join(temp_dir, self._asset_name)
            with open(temp_path, 'wb') as f:
                for chunk in chunks:
                    f.write(chunk)
            
            return temp_path
    
    def _emit_failure(self, errors):
        """生成详细的失败报告并发送信号"""
        error_lines = []
        for source_name, err_msg in errors:
            error_lines.append(f'  • {source_name}: {err_msg}')
        
        error_detail = '\n'.join(error_lines) if error_lines else '  • 无可用错误信息'
        
        msg = (
            f'所有下载源均不可用，更新下载失败。\n\n'
            f'尝试过的下载源:\n{error_detail}\n\n'
            f'原始链接:\n{self._download_url}\n\n'
            f'建议:\n'
            f'  1. 检查网络连接是否正常\n'
            f'  2. 尝试关闭 VPN 或代理后重试\n'
            f'  3. 前往 GitHub Releases 页面手动下载:\n'
            f'     https://github.com/{GITHUB_REPO}/releases'
        )
        self.download_failed.emit(msg)


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
        self.setFixedSize(480, 200)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # 状态标签（显示当前阶段）
        self._status_label = QLabel('正在测试下载源连通性...')
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)
        
        # 下载源标签
        self._source_label = QLabel('')
        self._source_label.setStyleSheet('color: #4a86e8; font-weight: bold;')
        self._source_label.setWordWrap(True)
        layout.addWidget(self._source_label)
        
        # 进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)
        
        # 进度文本
        self._progress_label = QLabel('')
        self._progress_label.setStyleSheet('color: #666; font-size: 9pt;')
        layout.addWidget(self._progress_label)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton('取消下载')
        cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
    
    def set_progress(self, percent):
        self._progress_bar.setValue(percent)
        self._progress_label.setText(f'下载进度: {percent}%')
    
    def set_status(self, text):
        self._status_label.setText(text)
    
    def set_source(self, source_name):
        self._source_label.setText(f'下载源: {source_name}')
    
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

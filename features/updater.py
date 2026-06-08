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

# ==================== 常量 ====================

GITHUB_REPO = 'mawenshui/bianqian_windows'
GITHUB_API_LATEST = f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'

# 下载超时（秒）
GITHUB_DOWNLOAD_TIMEOUT = 60       # GitHub 主链接
MIRROR_DOWNLOAD_TIMEOUT = 120      # 镜像备用链接（较慢）
VERSION_CHECK_TIMEOUT = 15         # 版本检查请求

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
    
    update_available = pyqtSignal(dict)
    no_update = pyqtSignal()
    check_failed = pyqtSignal(str)
    
    def __init__(self, current_version):
        super().__init__()
        self._current_version = current_version
    
    def run(self):
        try:
            req = urllib.request.Request(
                GITHUB_API_LATEST,
                headers={'Accept': 'application/vnd.github+json'}
            )
            with urllib.request.urlopen(req, timeout=VERSION_CHECK_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
            
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
                
        except (urllib.error.URLError, socket.timeout) as e:
            self.check_failed.emit(f'网络连接失败: {e}')
        except urllib.error.HTTPError as e:
            if e.code == 403:
                self.check_failed.emit('GitHub API 请求受限 (403)，请稍后重试')
            else:
                self.check_failed.emit(f'服务器错误 (HTTP {e.code})')
        except json.JSONDecodeError:
            self.check_failed.emit('服务器返回数据格式异常')
        except Exception as e:
            self.check_failed.emit(f'检查更新时发生未知错误: {e}')


# ==================== UpdateDownloader ====================

class UpdateDownloader(QThread):
    """后台下载更新文件，内置主/备双链路"""
    
    progress = pyqtSignal(int)
    download_finished = pyqtSignal(str)
    download_failed = pyqtSignal(str)
    
    def __init__(self, download_url, asset_name, install_type):
        super().__init__()
        self._download_url = download_url
        self._asset_name = asset_name
        self._install_type = install_type
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

def prepare_update_helper(install_type):
    """
    生成 PowerShell 辅助脚本内容。
    
    该脚本会在主进程退出后执行：
    - portable: 等待进程退出 → 移动新文件覆盖旧文件 → 重新启动
    - msi: 等待进程退出 → 执行 msiexec /i → 自动升级
    """
    if install_type == 'msi':
        # MSI 升级策略：获取 MSI 文件路径，执行静默升级
        return r'''
param(
    [string]$ExePath,
    [string]$NewFilePath,
    [string]$WindowPosFile
)

$ErrorActionPreference = 'Stop'

# 等待旧进程退出
Start-Sleep -Seconds 2
$timeout = 30
while ($timeout -gt 0) {
    $proc = Get-Process -Name 'StickyNote' -ErrorAction SilentlyContinue
    if (-not $proc) { break }
    Start-Sleep -Seconds 1
    $timeout--
}

try {
    # MSI 静默升级
    Start-Process -FilePath 'msiexec.exe' -ArgumentList "/i `"$NewFilePath`" /quiet /norestart" -Wait
    
    # 启动新版本
    Start-Process -FilePath $ExePath
} catch {
    Write-Error "MSI 升级失败: $_"
}
'''
    else:
        # Portable / Source: 直接替换 exe
        return r'''
param(
    [string]$ExePath,
    [string]$NewFilePath,
    [string]$WindowPosFile
)

$ErrorActionPreference = 'Stop'

# 等待旧进程退出
Start-Sleep -Seconds 2
$timeout = 30
while ($timeout -gt 0) {
    $proc = Get-Process -Name 'StickyNote' -ErrorAction SilentlyContinue
    if (-not $proc) { break }
    Start-Sleep -Seconds 1
    $timeout--
}

try {
    # 覆盖旧文件
    Copy-Item -Path $NewFilePath -Destination $ExePath -Force
    
    # 清理临时目录
    $tempDir = Split-Path -Parent $NewFilePath
    Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    
    # 启动新版本
    Start-Process -FilePath $ExePath
} catch {
    Write-Error "文件替换失败: $_"
}
'''


def execute_update(manager, new_file_path, install_type):
    """
    执行更新流程的最后一步：保存窗口位置 → 生成辅助脚本 → 启动脚本并退出应用。
    
    Args:
        manager: 主窗口 Manager 实例
        new_file_path: 下载的新文件路径 (.exe 或 .msi)
        install_type: 安装类型 ('msi' | 'portable' | 'source')
    """
    # 保存窗口位置
    if hasattr(manager, 'save_window_positions'):
        try:
            manager.save_window_positions()
        except Exception:
            pass
    
    # 生成 PowerShell 脚本
    helper_script = prepare_update_helper(install_type)
    script_path = os.path.join(tempfile.gettempdir(), 'stickynote_update_helper.ps1')
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(helper_script)
    
    # 获取窗口位置文件路径
    pos_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', 'window_positions.json'
    )
    pos_file = os.path.normpath(pos_file)
    
    # 启动辅助脚本（使用 -WindowStyle Hidden 隐藏 PowerShell 窗口）
    try:
        subprocess.Popen(
            [
                'powershell.exe', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass',
                '-File', script_path,
                '-ExePath', sys.executable,
                '-NewFilePath', new_file_path,
                '-WindowPosFile', pos_file
            ],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
    except Exception:
        # 备用方案: 直接退出，需要用户手动更新
        pass
    
    # 退出应用
    from PyQt5.QtWidgets import QApplication
    QApplication.instance().quit()

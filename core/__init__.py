# -*- coding: utf-8 -*-
"""
StickyNote 核心模块

本模块包含应用的核心功能组件：
- manager: 应用管理器 (StickyNoteManager)
- note: 便签窗口 (StickyNote, PlainLineEdit, PlainTextEdit, NoteSaveWorker)
- settings: 设置对话框 (SettingsDialog)
"""

import os
import shutil
import sys


def get_project_root():
    """
    获取项目根目录路径。
    
    兼容开发模式和 PyInstaller / cx_Freeze 打包后的冻结模式：
    - 开发模式：返回 __file__ 向上两层（bianqian_windows/）
    - Frozen 模式：返回 sys._MEIPASS（打包后的资源目录）
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller / cx_Freeze 打包后的资源根目录
        return sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_styles_dir():
    """获取 styles 主题目录的绝对路径"""
    return os.path.join(get_project_root(), 'styles')


def get_assets_dir():
    """获取应用静态资源目录的绝对路径。"""
    return os.path.join(get_project_root(), 'assets')


_LEGACY_USER_DATA_ENTRIES = (
    'notes',
    'backups',
    'templates',
    'logs',
    'settings.json',
    'tags.json',
    'window_positions.json',
)


def _migrate_legacy_development_data(project_root, data_dir):
    """将旧版开发数据从仓库根目录迁移到 runtime/，已有目标不覆盖。"""
    os.makedirs(data_dir, exist_ok=True)
    for entry in _LEGACY_USER_DATA_ENTRIES:
        source = os.path.join(project_root, entry)
        target = os.path.join(data_dir, entry)
        if not os.path.exists(source) or os.path.exists(target):
            continue
        try:
            shutil.move(source, target)
        except OSError:
            # 数据迁移失败不应阻止应用启动；保留源文件供用户手工处理。
            continue


def get_user_data_dir():
    """
    获取用户数据目录路径（notes, settings.json 等可写数据）。
    
    兼容开发模式和 PyInstaller / cx_Freeze 打包后的冻结模式：
    - 开发模式：返回项目根目录下的 runtime/，避免运行数据污染仓库根目录
    - Frozen 模式：返回 exe 所在目录（便携式部署，数据与 exe 同目录）
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        project_root = get_project_root()
        data_dir = os.path.join(project_root, 'runtime')
        _migrate_legacy_development_data(project_root, data_dir)
        return data_dir


__version__ = '1.7.8'
__author__ = 'MaWenshui'

from core.note import StickyNote, PlainLineEdit, PlainTextEdit, NoteSaveWorker, NoteLoadWorker, RESIZE_MARGIN
from core.settings import SettingsDialog

from core.manager import StickyNoteManager

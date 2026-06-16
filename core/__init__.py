# -*- coding: utf-8 -*-
"""
StickyNote 核心模块

本模块包含应用的核心功能组件：
- manager: 应用管理器 (StickyNoteManager)
- note: 便签窗口 (StickyNote, PlainLineEdit, PlainTextEdit, NoteSaveWorker)
- settings: 设置对话框 (SettingsDialog)
"""

import os
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


def get_user_data_dir():
    """
    获取用户数据目录路径（notes, settings.json 等可写数据）。
    
    兼容开发模式和 PyInstaller / cx_Freeze 打包后的冻结模式：
    - 开发模式：返回当前工作目录
    - Frozen 模式：返回 exe 所在目录（便携式部署，数据与 exe 同目录）
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.getcwd()


__version__ = '1.7.1'
__author__ = 'MaWenshui'

from core.note import StickyNote, PlainLineEdit, PlainTextEdit, NoteSaveWorker, NoteLoadWorker, RESIZE_MARGIN
from core.settings import SettingsDialog

from core.manager import StickyNoteManager

# -*- coding: utf-8 -*-
"""
cx_Freeze 打包配置 — 生成 MSI 安装包
"""
import sys
import os
from cx_Freeze import setup, Executable

# 项目根目录
project_dir = os.path.dirname(os.path.abspath(__file__))

# 需要包含的数据文件
include_files = [
    (os.path.join(project_dir, 'styles'), 'styles'),
]

# 构建选项
build_exe_options = {
    'build_exe': 'dist/StickyNote',
    'packages': [
        'PyQt5', 'pywintypes', 'win32api', 'win32con', 'win32gui',
    ],
    'includes': [
        'win32timezone', 'pythoncom',
    ],
    'include_files': include_files,
    'excludes': [
        'tkinter', 'unittest', 'email', 'xmlrpc',
        # 排除未使用的 PyQt5 子模块，避免 cx_Freeze 寻找缺失的 QML 等路径
        'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtQuickWidgets',
        'PyQt5.QtSql', 'PyQt5.QtNetwork', 'PyQt5.QtSvg',
        'PyQt5.QtXml', 'PyQt5.QtWebEngine', 'PyQt5.QtMultimedia',
        'PyQt5.QtMultimediaWidgets', 'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtWebChannel', 'PyQt5.QtOpenGL', 'PyQt5.QtPrintSupport',
    ],
}

# MSI 安装包选项
bdist_msi_options = {
    'add_to_path': False,
    'upgrade_code': '{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}',
    'initial_target_dir': r'[ProgramFilesFolder]',
    'summary_data': {
        'author': 'MaWenshui',
        'comments': '桌面便签应用',
        'keywords': 'sticky,note,便签,桌面',
    },
    'install_icon': os.path.join(project_dir, 'icon.png') if os.path.exists(os.path.join(project_dir, 'icon.png')) else None,
}

# 可执行文件配置
executables = [
    Executable(
        os.path.join(project_dir, 'main.py'),
        base='gui' if sys.platform == 'win32' else None,
        target_name='StickyNote.exe',
        icon=os.path.join(project_dir, 'icon.png') if os.path.exists(os.path.join(project_dir, 'icon.png')) else None,
        shortcut_name='桌面便签',
        shortcut_dir='DesktopFolder',
    )
]

setup(
    name='StickyNote',
    version='1.5.0',
    description='桌面便签应用 — 一款轻量级的 Windows 桌面便签工具',
    author='MaWenshui',
    options={
        'build_exe': build_exe_options,
        'bdist_msi': bdist_msi_options,
    },
    executables=executables,
)

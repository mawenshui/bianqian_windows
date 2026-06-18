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
    (os.path.join(project_dir, 'plugins'), 'plugins'),
    (os.path.join(project_dir, 'readme.md'), 'readme.md'),
]

# 构建选项
build_exe_options = {
    'build_exe': 'dist/StickyNote',
    'packages': [
        'PyQt5', 'pywintypes', 'win32api', 'win32con', 'win32gui',
        'cryptography', 'argon2', 'markdown', 'pygments',
    ],
    'includes': [
        'win32timezone', 'pythoncom',
        # 显式包含动态导入的关键模块（防止 cx_Freeze 静态分析遗漏）
        'features.help_content', 'features.markdown_renderer',
    ],
    'include_files': include_files,
    'excludes': [
        'tkinter', 'unittest', 'email', 'xmlrpc',
        # 排除未使用的 PyQt5 子模块，避免 cx_Freeze 寻找缺失的 QML 等路径
        'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtQuickWidgets',
        'PyQt5.QtSql', 'PyQt5.QtNetwork', 'PyQt5.QtSvg',
        'PyQt5.QtXml', 'PyQt5.QtWebEngine', 'PyQt5.QtMultimedia',
        'PyQt5.QtMultimediaWidgets', 'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtWebChannel', 'PyQt5.QtOpenGL',
    ],
}

# MSI 安装包选项
bdist_msi_options = {
    'add_to_path': False,
    'upgrade_code': '{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}',
    'initial_target_dir': r'[ProgramFilesFolder]',
    'summary_data': {
        'author': 'MaWenshui',
        'comments': '桌面便签应用 — 一款轻量级的 Windows 桌面便签工具',
        'keywords': 'sticky,note,便签,桌面',
    },
    'install_icon': os.path.join(project_dir, 'icon.png') if os.path.exists(os.path.join(project_dir, 'icon.png')) else None,
    # 安装完成后显示"立即运行"复选框
    'launch_on_finish': True,
    # 自定义 MSI 表数据
    'data': {
        # --- 桌面快捷方式 Property（默认勾选）---
        'Property': [
            ('DESKTOPSHORTCUT', '1'),
        ],

        # --- 中文化按钮文本（通过 UIText 覆写）---
        'UIText': [
            ('ButtonText_Back',   '上一步(&B)'),
            ('ButtonText_Browse', '浏览(&R)...'),
            ('ButtonText_Cancel', '取消'),
            ('ButtonText_Exit',   '退出'),
            ('ButtonText_Finish', '完成(&F)'),
            ('ButtonText_Ignore', '忽略(&I)'),
            ('ButtonText_Install','安装(&I)'),
            ('ButtonText_Next',   '下一步(&N)'),
            ('ButtonText_No',     '否(&N)'),
            ('ButtonText_OK',     '确定'),
            ('ButtonText_Remove', '删除(&R)'),
            ('ButtonText_Repair', '修复(&R)'),
            ('ButtonText_Retry',  '重试(&R)'),
            ('ButtonText_Yes',    '是(&Y)'),
            ('Progress1',         '正在安装'),
            ('Progress2',         '正在安装'),
            ('MaintenanceForm_Action', '修复'),
        ],

        # --- 目录自动追加 StickyNote\ 子目录 ---
        'CustomAction': [
            # 类型 51: 将 TARGETDIR 设置为 [TARGETDIR]StickyNote\（追加子目录）
            ('A_APPEND_STICKYNOTE_DIR', 51, 'TARGETDIR', '[TARGETDIR]StickyNote' + '\\'),
        ],
        'InstallUISequence': [
            # 在 SelectDirectoryDlg(1230) 之后、ProgressDlg(1280) 之前执行
            ('A_APPEND_STICKYNOTE_DIR', 'NOT Installed', 1235),
        ],
        'InstallExecuteSequence': [
            # 静默安装时也同样追加子目录
            ('A_APPEND_STICKYNOTE_DIR', 'NOT Installed', 1235),
        ],

        # --- 桌面快捷方式：组件 + 注册表KeyPath + 快捷方式 + 功能绑定 ---
        'Component': [
            # 条件化组件：仅当 DESKTOPSHORTCUT=1 时安装
            # Attributes=4 (RegistryKeyPath): KeyPath 指向注册表项
            ('DesktopShortcut', '{B8C2D4E6-F1A3-5B7D-9E0F-2A4C6D8E0F1A}', 'DesktopFolder', 4, 'DESKTOPSHORTCUT', 'DesktopShortcutReg'),
        ],
        'Registry': [
            # Registry, Root, Key, Name, Value, Component_
            # Root=1 (HKCR); 注册表项作为组件 KeyPath，卸载时自动清理
            ('DesktopShortcutReg', 1,
             'Software\\StickyNote\\DesktopShortcut',
             'Installed', '1', 'DesktopShortcut'),
        ],
        'Shortcut': [
            # Shortcut, Directory_, Name, Component_, Target, Arguments, Description, Hotkey, Icon_, IconIndex, ShowCmd, WkDir
            ('DesktopShortcut', 'DesktopFolder', '便签.lnk', 'DesktopShortcut',
             '[TARGETDIR]StickyNote.exe', '', '桌面便签应用', '', '', '', '', ''),
        ],
        'FeatureComponents': [
            ('default', 'DesktopShortcut'),
        ],

        # --- ExitDialog 中添加"创建桌面快捷方式"复选框 ---
        'Control': [
            # Dialog_, Control, Type, X, Y, Width, Height, Attributes, Property, Text, Control_Next, Help
            # LaunchOnFinish 在 Y=200，Description 在 Y=235，此处放在中间 Y=220
            ('ExitDialog', 'DesktopShortcut', 'CheckBox', 15, 220, 300, 20, 3,
             'DESKTOPSHORTCUT', '创建桌面快捷方式(&D)', '', ''),
        ],
        'ControlCondition': [
            # 修复/卸载时不显示桌面快捷方式复选框
            ('ExitDialog', 'DesktopShortcut', 'Hide', 'Installed'),
        ],
    },
}

# 可执行文件配置
executables = [
    Executable(
        os.path.join(project_dir, 'main.py'),
        base='gui' if sys.platform == 'win32' else None,
        target_name='StickyNote.exe',
        icon=os.path.join(project_dir, 'icon.png') if os.path.exists(os.path.join(project_dir, 'icon.png')) else None,
    )
]

setup(
    name='StickyNote',
    version='1.7.6',
    description='桌面便签应用 — 一款轻量级的 Windows 桌面便签工具',
    author='MaWenshui',
    options={
        'build_exe': build_exe_options,
        'bdist_msi': bdist_msi_options,
    },
    executables=executables,
)

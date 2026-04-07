import sys
import os
import json

# 平台检测
import platform
is_windows = platform.system() == 'Windows'

if is_windows:
    import winreg
from functools import partial
from PyQt5.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox,
    QDialog, QTabWidget, QWidget, QVBoxLayout, QFormLayout, QLabel,
    QComboBox, QGroupBox, QFrame, QLineEdit, QTextEdit, QFontComboBox,
    QSpinBox, QCheckBox, QHBoxLayout, QPushButton
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWidgets import QStyle

# 导入新功能模块
from features.search import SearchManager
from features.shortcuts import ShortcutManager
from features.backup import BackupManager
from features.positioning import get_position_manager
from features.export_import import ExportImportManager
from features.trash import TrashManager
from features.version_history import VersionHistoryManager
from core.sticky_note import StickyNote

class SettingsDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowModality(Qt.NonModal)  # 设置为非模态对话框
        self.initUI()

    def initUI(self):
        self.setWindowTitle('设置')
        self.setFixedSize(600, 500)  # 增加窗口大小以容纳新功能
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)  # 始终置顶
        
        # 使用标签页布局
        tab_widget = QTabWidget()
        
        # 主题设置标签页
        theme_tab = QWidget()
        self.setup_theme_tab(theme_tab)
        tab_widget.addTab(theme_tab, "主题设置")
        
        # 字体设置标签页
        font_tab = QWidget()
        self.setup_font_tab(font_tab)
        tab_widget.addTab(font_tab, "字体设置")
        
        # 快捷键设置标签页
        shortcut_tab = QWidget()
        self.setup_shortcut_tab(shortcut_tab)
        tab_widget.addTab(shortcut_tab, "快捷键设置")
        
        # 语言设置标签页
        language_tab = QWidget()
        self.setup_language_tab(language_tab)
        tab_widget.addTab(language_tab, "语言设置")
        
        main_layout = QVBoxLayout()
        main_layout.addWidget(tab_widget)
        
        # 作者标签
        author_label = QLabel("By：MaWenshui")
        author_label.setAlignment(Qt.AlignCenter)
        author_label.setStyleSheet("color: gray; font-size: 10pt;")
        main_layout.addWidget(author_label)
        
        self.setLayout(main_layout)
    
    def setup_theme_tab(self, tab_widget):
        """设置主题标签页"""
        layout = QVBoxLayout()
        
        # 主题选择区域
        theme_group = QGroupBox("主题选择")
        theme_layout = QFormLayout()
        
        self.theme_label = QLabel("选择便签默认主题:")
        self.theme_combo = QComboBox()
        
        # 动态加载主题
        self.load_themes()
        
        current_theme_css = self.manager.get_default_theme_css()
        current_theme_name = self.manager.get_theme_name_by_css(current_theme_css)
        if current_theme_name:
            index = self.theme_combo.findText(current_theme_name)
            if index != -1:
                self.theme_combo.setCurrentIndex(index)
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        
        theme_layout.addRow(self.theme_label, self.theme_combo)
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)
        
        # 主题预览区域
        preview_group = QGroupBox("主题预览")
        preview_layout = QVBoxLayout()
        
        # 创建预览便签
        self.preview_note = QFrame()
        self.preview_note.setFixedSize(280, 200)
        self.preview_note.setFrameStyle(QFrame.StyledPanel)
        
        preview_note_layout = QVBoxLayout()
        
        # 预览标题
        self.preview_title = QLineEdit("预览标题")
        self.preview_title.setReadOnly(True)
        preview_note_layout.addWidget(self.preview_title)
        
        # 预览内容
        self.preview_content = QTextEdit()
        self.preview_content.setPlainText("这是主题预览内容\n可以看到当前主题的样式效果")
        self.preview_content.setReadOnly(True)
        preview_note_layout.addWidget(self.preview_content)
        
        self.preview_note.setLayout(preview_note_layout)
        preview_layout.addWidget(self.preview_note)
        
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)
        
        # 更新预览
        self.update_theme_preview()
        
        tab_widget.setLayout(layout)
    
    def setup_font_tab(self, tab_widget):
        """设置字体标签页"""
        layout = QVBoxLayout()
        
        # 字体选择区域
        font_group = QGroupBox("字体设置")
        font_layout = QFormLayout()
        
        # 字体族选择
        self.font_family_combo = QFontComboBox()
        current_font = self.manager.get_default_font()
        if current_font:
            self.font_family_combo.setCurrentFont(QFont(current_font['family']))
        self.font_family_combo.currentFontChanged.connect(self.on_font_changed)
        font_layout.addRow("字体族:", self.font_family_combo)
        
        # 字体大小
        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setRange(8, 72)
        self.font_size_spinbox.setValue(current_font.get('size', 12) if current_font else 12)
        self.font_size_spinbox.setSuffix(' pt')
        self.font_size_spinbox.valueChanged.connect(self.on_font_changed)
        font_layout.addRow("字体大小:", self.font_size_spinbox)
        
        # 字体样式
        font_style_layout = QHBoxLayout()
        self.font_bold_checkbox = QCheckBox("粗体")
        self.font_italic_checkbox = QCheckBox("斜体")
        if current_font:
            self.font_bold_checkbox.setChecked(current_font.get('bold', False))
            self.font_italic_checkbox.setChecked(current_font.get('italic', False))
        self.font_bold_checkbox.stateChanged.connect(self.on_font_changed)
        self.font_italic_checkbox.stateChanged.connect(self.on_font_changed)
        font_style_layout.addWidget(self.font_bold_checkbox)
        font_style_layout.addWidget(self.font_italic_checkbox)
        font_style_layout.addStretch()
        font_layout.addRow("字体样式:", font_style_layout)
        
        font_group.setLayout(font_layout)
        layout.addWidget(font_group)
        
        # 字体预览区域
        font_preview_group = QGroupBox("字体预览")
        font_preview_layout = QVBoxLayout()
        
        self.font_preview_label = QLabel("这是字体预览文本\nABCDEFG abcdefg 12345")
        self.font_preview_label.setAlignment(Qt.AlignCenter)
        self.font_preview_label.setStyleSheet("border: 1px solid gray; padding: 20px; background-color: white;")
        self.font_preview_label.setMinimumHeight(100)
        
        font_preview_layout.addWidget(self.font_preview_label)
        font_preview_group.setLayout(font_preview_layout)
        layout.addWidget(font_preview_group)
        
        # 重置按钮
        reset_layout = QHBoxLayout()
        reset_layout.addStretch()
        reset_font_btn = QPushButton("重置为默认字体")
        reset_font_btn.clicked.connect(self.reset_font_settings)
        reset_layout.addWidget(reset_font_btn)
        layout.addLayout(reset_layout)
        
        # 更新字体预览
        self.update_font_preview()
        
        tab_widget.setLayout(layout)

    def load_themes(self):
        self.themes = self.manager.get_available_themes()
        self.theme_combo.clear()
        for theme_name in self.themes.keys():
            self.theme_combo.addItem(theme_name)

    def on_theme_changed(self):
        """主题改变时的处理"""
        selected_theme_name = self.theme_combo.currentText()
        selected_theme_css = self.themes.get(selected_theme_name, "soft_yellow.css")
        self.manager.set_default_theme(selected_theme_css)
        self.manager.apply_theme_to_all_notes()
        self.update_theme_preview()
    
    def update_theme_preview(self):
        """更新主题预览"""
        if hasattr(self, 'preview_note'):
            selected_theme_name = self.theme_combo.currentText()
            selected_theme_css = self.themes.get(selected_theme_name, "soft_yellow.css")
            
            # 读取主题CSS文件
            css_path = os.path.join('styles', selected_theme_css)
            if os.path.exists(css_path):
                with open(css_path, 'r', encoding='utf-8') as f:
                    css_content = f.read()
                
                # 应用样式到预览组件
                self.preview_title.setStyleSheet(css_content)
                self.preview_content.setStyleSheet(css_content)
                self.preview_note.setStyleSheet(css_content)
    
    def on_font_changed(self):
        """字体改变时的处理"""
        font_settings = {
            'family': self.font_family_combo.currentFont().family(),
            'size': self.font_size_spinbox.value(),
            'bold': self.font_bold_checkbox.isChecked(),
            'italic': self.font_italic_checkbox.isChecked()
        }
        
        # 保存字体设置
        self.manager.set_default_font(font_settings)
        
        # 更新字体预览
        self.update_font_preview()
        
        # 应用到所有便签
        self.manager.apply_font_to_all_notes()
    
    def update_font_preview(self):
        """更新字体预览"""
        if hasattr(self, 'font_preview_label'):
            font = QFont()
            font.setFamily(self.font_family_combo.currentFont().family())
            font.setPointSize(self.font_size_spinbox.value())
            font.setBold(self.font_bold_checkbox.isChecked())
            font.setItalic(self.font_italic_checkbox.isChecked())
            
            self.font_preview_label.setFont(font)
    
    def reset_font_settings(self):
        """重置字体设置为默认值"""
        self.font_family_combo.setCurrentFont(QFont("微软雅黑"))
        self.font_size_spinbox.setValue(12)
        self.font_bold_checkbox.setChecked(False)
        self.font_italic_checkbox.setChecked(False)
        
        # 触发字体更新
        self.on_font_changed()
    
    def setup_shortcut_tab(self, tab_widget):
        """设置快捷键标签页"""
        layout = QVBoxLayout()
        
        # 快捷键设置区域
        shortcut_group = QGroupBox("全局快捷键设置")
        shortcut_layout = QFormLayout()
        
        # 加载当前快捷键设置
        self.shortcuts = {
            'add_note': 'Ctrl+Shift+N',
            'show_search_dialog': 'Ctrl+Shift+F',
            'show_backup_dialog': 'Ctrl+Shift+B'
        }
        
        # 添加便签快捷键
        self.add_note_shortcut_edit = QLineEdit(self.shortcuts['add_note'])
        shortcut_layout.addRow("添加便签:", self.add_note_shortcut_edit)
        
        # 搜索便签快捷键
        self.search_shortcut_edit = QLineEdit(self.shortcuts['show_search_dialog'])
        shortcut_layout.addRow("搜索便签:", self.search_shortcut_edit)
        
        # 备份管理快捷键
        self.backup_shortcut_edit = QLineEdit(self.shortcuts['show_backup_dialog'])
        shortcut_layout.addRow("备份管理:", self.backup_shortcut_edit)
        
        shortcut_group.setLayout(shortcut_layout)
        layout.addWidget(shortcut_group)
        
        # 保存按钮
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        save_shortcut_btn = QPushButton("保存快捷键设置")
        save_shortcut_btn.clicked.connect(self.save_shortcut_settings)
        save_layout.addWidget(save_shortcut_btn)
        layout.addLayout(save_layout)
        
        tab_widget.setLayout(layout)
    
    def save_shortcut_settings(self):
        """保存快捷键设置"""
        # 获取新的快捷键设置
        new_shortcuts = {
            'add_note': self.add_note_shortcut_edit.text(),
            'show_search_dialog': self.search_shortcut_edit.text(),
            'show_backup_dialog': self.backup_shortcut_edit.text()
        }
        
        # 这里可以添加快捷键验证逻辑
        
        # 保存到设置
        self.manager.settings['shortcuts'] = new_shortcuts
        self.manager.save_settings()
        
        # 重新注册快捷键
        self.manager.shortcut_manager.cleanup()
        self.manager.setup_global_shortcuts()
        
        QMessageBox.information(self, "快捷键设置", "快捷键设置已保存")
    
    def setup_language_tab(self, tab_widget):
        """设置语言标签页"""
        layout = QVBoxLayout()
        
        # 语言选择区域
        language_group = QGroupBox("语言选择")
        language_layout = QFormLayout()
        
        self.language_label = QLabel("选择界面语言:")
        self.language_combo = QComboBox()
        
        # 加载可用语言
        self.languages = {
            'zh_CN': '简体中文',
            'en_US': 'English'
        }
        
        for lang_code, lang_name in self.languages.items():
            self.language_combo.addItem(lang_name, lang_code)
        
        # 设置当前语言
        current_language = self.manager.settings.get('language', 'zh_CN')
        index = self.language_combo.findData(current_language)
        if index != -1:
            self.language_combo.setCurrentIndex(index)
        
        language_layout.addRow(self.language_label, self.language_combo)
        language_group.setLayout(language_layout)
        layout.addWidget(language_group)
        
        # 保存按钮
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        save_language_btn = QPushButton("保存语言设置")
        save_language_btn.clicked.connect(self.save_language_settings)
        save_layout.addWidget(save_language_btn)
        layout.addLayout(save_layout)
        
        tab_widget.setLayout(layout)
    
    def save_language_settings(self):
        """保存语言设置"""
        # 获取选中的语言
        selected_index = self.language_combo.currentIndex()
        selected_language = self.language_combo.itemData(selected_index)
        
        # 保存到设置
        self.manager.settings['language'] = selected_language
        self.manager.save_settings()
        
        QMessageBox.information(self, "语言设置", "语言设置已保存，重启应用后生效")
    
    def change_theme(self):
        """保持向后兼容性"""
        self.on_theme_changed()

class StickyNoteManager:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # 设置应用图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'icon.png')  # 确保存在icon.png
        if not os.path.exists(icon_path):
            # 如果没有自定义图标，使用默认图标
            self.icon = self.app.style().standardIcon(QStyle.SP_DesktopIcon)
        else:
            self.icon = QIcon(icon_path)
        self.app.setWindowIcon(self.icon)

        self.notes = {}
        self.notes_dir = os.path.join(os.getcwd(), 'notes')
        self.notes_dir = os.path.abspath(self.notes_dir)  # 转换为绝对路径
        os.makedirs(self.notes_dir, exist_ok=True)

        # 加载或初始化设置
        self.settings_file = os.path.join(os.getcwd(), 'settings.json')
        self.settings_file = os.path.abspath(self.settings_file)  # 转换为绝对路径
        self.settings = self.load_settings()
        
        # 初始化默认字体设置
        if 'font' not in self.settings:
            self.settings['font'] = {
                'family': '微软雅黑',
                'size': 12,
                'bold': False,
                'italic': False
            }
            self.save_settings()

        # 初始化新功能模块
        self.search_manager = SearchManager(self)
        self.shortcut_manager = ShortcutManager()
        self.backup_manager = BackupManager(self)
        self.export_import_manager = ExportImportManager(self)
        self.trash_manager = TrashManager(self)
        self.version_history_manager = VersionHistoryManager(self)
        self.position_manager = get_position_manager()
        
        # 初始化标签管理
        from features.tags import TagManager
        self.tag_manager = TagManager(self)
        
        # 初始化分组管理
        from features.groups import GroupManager
        self.group_manager = GroupManager(self)
        
        # 注册全局快捷键
        self.setup_global_shortcuts()

        # 设置托盘图标和菜单
        self.setup_tray_icon()

        # 加载已有便签
        self.load_notes()

        # 启动时默认创建一个便签（如果没有）
        if not self.notes:
            self.add_note()

        # 初始化设置对话框实例为空
        self.settings_dialog = None

    def setup_global_shortcuts(self):
        """
        设置全局快捷键
        """
        try:
            # 加载保存的快捷键设置
            shortcuts = self.settings.get('shortcuts', {
                'add_note': 'Ctrl+Shift+N',
                'show_search_dialog': 'Ctrl+Shift+F',
                'show_backup_dialog': 'Ctrl+Shift+B'
            })
            
            # 注册创建新便签的快捷键
            self.shortcut_manager.register_global_shortcut(
                shortcuts.get('add_note', 'Ctrl+Shift+N'), 
                'add_note'
            )
            
            # 注册搜索便签的快捷键
            self.shortcut_manager.register_global_shortcut(
                shortcuts.get('show_search_dialog', 'Ctrl+Shift+F'), 
                'show_search_dialog'
            )
            
            # 注册备份管理的快捷键
            self.shortcut_manager.register_global_shortcut(
                shortcuts.get('show_backup_dialog', 'Ctrl+Shift+B'), 
                'show_backup_dialog'
            )
            
            # 连接快捷键信号到对应方法
            self.shortcut_manager.shortcut_activated.connect(self.handle_shortcut_activated)
            
        except Exception as e:
            print(f"设置全局快捷键时出错: {e}")
    
    def show_search_dialog(self):
        """
        显示搜索对话框
        """
        self.search_manager.show_search_dialog()
    
    def show_backup_dialog(self):
        """
        显示备份管理对话框
        """
        self.backup_manager.show_backup_dialog()
    
    def show_export_dialog(self):
        """显示导出对话框"""
        self.export_import_manager.show_export_dialog()
    
    def show_import_dialog(self):
        """显示导入对话框"""
        self.export_import_manager.show_import_dialog()
    
    def show_trash_dialog(self):
        """显示回收站对话框"""
        self.trash_manager.show_trash_dialog()
    
    def handle_shortcut_activated(self, action_name):
        """
        处理快捷键激活事件
        
        Args:
            action_name: 动作名称
        """
        try:
            if action_name == 'add_note':
                self.add_note()
            elif action_name == 'show_search_dialog':
                self.show_search_dialog()
            elif action_name == 'show_backup_dialog':
                self.show_backup_dialog()
            else:
                print(f"未知的快捷键动作: {action_name}")
        except Exception as e:
            print(f"处理快捷键激活时出错: {e}")

    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self.icon, parent=self.app)
        self.tray_icon.setToolTip("桌面便签应用")

        self.tray_menu = QMenu()

        # 添加便签
        add_action = QAction("添加便签 (Ctrl+Shift+N)", self.app)
        add_action.triggered.connect(self.add_note)
        self.tray_menu.addAction(add_action)

        # 添加搜索选项
        search_action = QAction("搜索便签 (Ctrl+Shift+F)", self.app)
        search_action.triggered.connect(self.show_search_dialog)
        self.tray_menu.addAction(search_action)

        # 添加备份管理选项
        backup_action = QAction("备份管理 (Ctrl+Shift+B)", self.app)
        backup_action.triggered.connect(self.show_backup_dialog)
        self.tray_menu.addAction(backup_action)

        # 添加导出选项
        export_action = QAction("导出便签", self.app)
        export_action.triggered.connect(self.show_export_dialog)
        self.tray_menu.addAction(export_action)

        # 添加导入选项
        import_action = QAction("导入便签", self.app)
        import_action.triggered.connect(self.show_import_dialog)
        self.tray_menu.addAction(import_action)

        # 添加回收站选项
        trash_action = QAction("回收站", self.app)
        trash_action.triggered.connect(self.show_trash_dialog)
        self.tray_menu.addAction(trash_action)

        # 分割线
        self.tray_menu.addSeparator()

        # 创建便签列表的子菜单
        self.notes_menu = QMenu("便签", self.tray_menu)
        self.tray_menu.addMenu(self.notes_menu)
        
        # 创建分组列表的子菜单
        self.groups_menu = QMenu("分组", self.tray_menu)
        self.tray_menu.addMenu(self.groups_menu)

        # 分割线
        self.tray_menu.addSeparator()

        # 开机自启
        self.autostart_action = QAction("开机自启", self.app)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self.check_autostart())
        self.autostart_action.triggered.connect(self.toggle_autostart)
        self.tray_menu.addAction(self.autostart_action)

        # 设置
        settings_action = QAction("设置", self.app)
        settings_action.triggered.connect(self.open_settings)
        self.tray_menu.addAction(settings_action)

        # 退出
        exit_action = QAction("退出", self.app)
        exit_action.triggered.connect(self.exit_application)
        self.tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

        # 双击托盘图标显示一个便签（例如最近打开的便签）
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def update_tray_menu(self):
        # 清空便签子菜单
        self.notes_menu.clear()

        if not self.notes:
            no_notes_action = QAction("暂无便签", self.app)
            no_notes_action.setEnabled(False)
            self.notes_menu.addAction(no_notes_action)
        else:
            for note_id, note in sorted(self.notes.items()):
                note_title = note.note_data.get('title', f'便签 {note_id}')

                # 创建子菜单
                note_menu = QMenu(note_title, self.notes_menu)

                # 添加“打开”选项
                open_action = QAction("打开", self.app)
                open_action.triggered.connect(partial(self.open_note, note_id))  # 使用 partial 绑定 note_id
                note_menu.addAction(open_action)

                # 添加“删除”选项
                delete_action = QAction("删除", self.app)
                delete_action.triggered.connect(partial(self.delete_note, note_id))  # 使用 partial 绑定 note_id
                note_menu.addAction(delete_action)

                # 添加到便签子菜单
                self.notes_menu.addMenu(note_menu)
        
        # 更新分组子菜单
        self.groups_menu.clear()
        
        if hasattr(self, 'group_manager'):
            all_groups = self.group_manager.get_all_groups()
            if not all_groups:
                no_groups_action = QAction("暂无分组", self.app)
                no_groups_action.setEnabled(False)
                self.groups_menu.addAction(no_groups_action)
            else:
                for group in all_groups:
                    group_menu = QMenu(group, self.groups_menu)
                    group_notes = self.group_manager.get_group_notes(group)
                    
                    if not group_notes:
                        no_notes_action = QAction("无便签", self.app)
                        no_notes_action.setEnabled(False)
                        group_menu.addAction(no_notes_action)
                    else:
                        for note_id in group_notes:
                            if note_id in self.notes:
                                note = self.notes[note_id]
                                note_title = note.note_data.get('title', f'便签 {note_id}')
                                
                                open_action = QAction(note_title, self.app)
                                open_action.triggered.connect(partial(self.open_note, note_id))
                                group_menu.addAction(open_action)
                    
                    self.groups_menu.addMenu(group_menu)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            # 双击托盘图标打开最近一个便签
            if self.notes:
                # 获取最近打开的便签（假设为 ID 最大的便签）
                last_note_id = max(self.notes.keys())
                self.open_note(last_note_id)

    def add_note(self):
        note_id = self.generate_note_id()
        default_theme_css = self.get_default_theme_css()
        new_note = StickyNote(note_id, self.notes_dir, manager=self, theme_css=default_theme_css)
        new_note.show()
        self.notes[note_id] = new_note
        self.update_tray_menu()

    def open_note(self, note_id):
        if note_id in self.notes:
            note = self.notes[note_id]
            note.show()
            note.raise_()
            note.activateWindow()

    def delete_note(self, note_id):
        if note_id in self.notes:
            note = self.notes[note_id]
            note.delete_note()

    def remove_note(self, note_id):
        if note_id in self.notes:
            del self.notes[note_id]
            self.update_tray_menu()

    def load_notes(self):
        for filename in os.listdir(self.notes_dir):
            if filename.startswith('note_') and filename.endswith('.json'):
                try:
                    note_id_str = filename.split('_')[1].split('.')[0]
                    note_id = int(note_id_str)
                    if note_id in self.notes:
                        continue
                    # 获取主题CSS文件，如果设置了默认主题，使用默认主题
                    default_theme_css = self.get_default_theme_css()
                    new_note = StickyNote(note_id, self.notes_dir, manager=self, theme_css=default_theme_css)
                    new_note.show()
                    self.notes[note_id] = new_note
                except Exception as e:
                    print(f"加载便签时出错: {e}")
        self.update_tray_menu()

    def generate_note_id(self):
        existing_ids = set(self.notes.keys())
        note_id = 1
        while note_id in existing_ids:
            note_id += 1
        return note_id

    def open_settings(self):
        if not self.settings_dialog:
            self.settings_dialog = SettingsDialog(self)
            self.settings_dialog.setWindowModality(Qt.NonModal)  # 设置为非模态对话框
            self.settings_dialog.setAttribute(Qt.WA_DeleteOnClose, True)
            self.settings_dialog.destroyed.connect(self.on_settings_closed)
            self.settings_dialog.show()
        else:
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()

    def on_settings_closed(self):
        self.settings_dialog = None

    def set_autostart(self, enable=True):
        if not is_windows:
            QMessageBox.warning(None, '设置开机自启失败', '开机自启功能仅支持 Windows 系统。')
            return False
        
        exe_path = os.path.realpath(sys.argv[0])
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, run_key, 0, winreg.KEY_SET_VALUE)
            if enable:
                winreg.SetValueEx(key, "StickyNoteApp", 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, "StickyNoteApp")
                except FileNotFoundError:
                    pass  # 如果不存在则忽略
            winreg.CloseKey(key)
            return True
        except Exception as e:
            QMessageBox.warning(None, '设置开机自启失败', f'无法设置开机自启: {e}')
            return False

    def check_autostart(self):
        if not is_windows:
            return False
        
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, run_key, 0, winreg.KEY_READ)
            value, regtype = winreg.QueryValueEx(key, "StickyNoteApp")
            winreg.CloseKey(key)
            return True if value else False
        except FileNotFoundError:
            return False
        except Exception as e:
            QMessageBox.warning(None, '检查开机自启失败', f'无法检查开机自启状态: {e}')
            return False

    def toggle_autostart(self, checked):
        if not is_windows:
            QMessageBox.warning(None, '设置开机自启失败', '开机自启功能仅支持 Windows 系统。')
            self.autostart_action.setChecked(False)
            return
        
        if checked:
            success = self.set_autostart(True)
            if success:
                QMessageBox.information(None, '开机自启', '已启用开机自启。')
            else:
                self.autostart_action.setChecked(False)
        else:
            success = self.set_autostart(False)
            if success:
                QMessageBox.information(None, '开机自启', '已禁用开机自启。')
            else:
                self.autostart_action.setChecked(True)

    def exit_application(self):
        # 清理快捷键
        try:
            self.shortcut_manager.cleanup()
        except Exception as e:
            print(f"清理快捷键时出错: {e}")
        
        for note in list(self.notes.values()):
            note.close()
        self.tray_icon.hide()
        QApplication.quit()

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                QMessageBox.warning(None, '加载设置错误', f'无法加载设置文件: {e}')
                return {
                    'default_theme': "soft_yellow.css"
                }
        else:
            return {
                'default_theme': "soft_yellow.css"
            }

    def save_settings(self):
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            QMessageBox.warning(None, '保存设置错误', f'无法保存设置文件: {e}')

    def get_available_themes(self):
        """
        扫描 styles 文件夹，读取每个 CSS 文件的主题名称，并返回一个字典
        """
        themes = {}
        styles_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'styles')
        if not os.path.exists(styles_dir):
            os.makedirs(styles_dir, exist_ok=True)

        for filename in os.listdir(styles_dir):
            if filename.endswith('.css'):
                filepath = os.path.join(styles_dir, filename)
                theme_name = self.extract_theme_name_from_css(filepath)
                if theme_name:
                    themes[theme_name] = filename
        return themes

    def extract_theme_name_from_css(self, filepath):
        """
        从 CSS 文件中提取主题名称。假设主题名称在文件的第一行，如：
        /* Theme Name: 柔和黄色 */
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('/*') and 'Theme Name:' in line:
                        # 提取主题名称
                        start = line.find('Theme Name:') + len('Theme Name:')
                        end = line.find('*/', start)
                        if end == -1:
                            end = len(line)
                        theme_name = line[start:end].strip()
                        return theme_name
                    elif line and not line.startswith('/*'):
                        # 第一行不是主题名称注释，跳过
                        break
            return None
        except Exception as e:
            print(f"无法从 {filepath} 中提取主题名称: {e}")
            return None

    def get_theme_name_by_css(self, css_filename):
        """
        根据 CSS 文件名返回主题名称
        """
        for name, filename in self.get_available_themes().items():
            if filename == css_filename:
                return name
        return None

    def get_default_theme_css(self):
        return self.settings.get('default_theme', "soft_yellow.css")

    def set_default_theme(self, theme_css):
        self.settings['default_theme'] = theme_css
        self.save_settings()

    def apply_theme_to_all_notes(self):
        for note in self.notes.values():
            note.set_theme(self.get_default_theme_css())
    
    def get_default_font(self):
        """获取默认字体设置"""
        return self.settings.get('font', {
            'family': '微软雅黑',
            'size': 12,
            'bold': False,
            'italic': False
        })
    
    def set_default_font(self, font_settings):
        """设置默认字体"""
        self.settings['font'] = font_settings
        self.save_settings()
    
    def apply_font_to_all_notes(self):
        """应用字体设置到所有便签"""
        font_settings = self.get_default_font()
        for note in self.notes.values():
            note.set_font(font_settings)

    def run(self):
        sys.exit(self.app.exec_())
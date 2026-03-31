import sys
import os
import json
import winreg
from functools import partial
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QStyle

from core.note import StickyNote
from core.utils import LazyLoader, NoteCache
from features.shortcuts import ShortcutManager

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

        # 初始化性能优化模块
        self.lazy_loader = LazyLoader()
        self.note_cache = NoteCache(max_size=100)  # 缓存最多100个便签

        # 初始化新功能模块（使用延迟加载）
        self.shortcut_manager = ShortcutManager()
        
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
            # 注册创建新便签的快捷键 (Ctrl+Shift+N)
            self.shortcut_manager.register_global_shortcut(
                'Ctrl+Shift+N', 
                'add_note'
            )
            
            # 注册搜索便签的快捷键 (Ctrl+Shift+F)
            self.shortcut_manager.register_global_shortcut(
                'Ctrl+Shift+F', 
                'show_search_dialog'
            )
            
            # 注册备份管理的快捷键 (Ctrl+Shift+B)
            self.shortcut_manager.register_global_shortcut(
                'Ctrl+Shift+B', 
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
        # 延迟加载搜索模块
        if not hasattr(self, 'search_manager'):
            SearchManager = self.lazy_loader.load_module('search')
            self.search_manager = SearchManager(self)
        self.search_manager.show_search_dialog()
    
    def show_backup_dialog(self):
        """
        显示备份管理对话框
        """
        # 延迟加载备份模块
        if not hasattr(self, 'backup_manager'):
            BackupManager = self.lazy_loader.load_module('backup')
            self.backup_manager = BackupManager(self)
        self.backup_manager.show_backup_dialog()
    
    def get_position_manager(self):
        """
        获取位置管理器（延迟加载）
        """
        if not hasattr(self, 'position_manager'):
            get_position_manager = self.lazy_loader.load_module('positioning')
            self.position_manager = get_position_manager()
        return self.position_manager
    
    def get_reminder_manager(self):
        """
        获取提醒管理器（延迟加载）
        """
        if not hasattr(self, 'reminder_manager'):
            ReminderManager = self.lazy_loader.load_module('reminder')
            self.reminder_manager = ReminderManager(self)
        return self.reminder_manager
    
    def get_tag_manager(self):
        """
        获取标签管理器（延迟加载）
        """
        if not hasattr(self, 'tag_manager'):
            TagManager = self.lazy_loader.load_module('tags')
            self.tag_manager = TagManager(self)
        return self.tag_manager
    
    def show_tag_management(self):
        """
        显示标签管理界面
        """
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QMessageBox
        from PyQt5.QtCore import Qt
        
        tag_manager = self.get_tag_manager()
        all_tags = tag_manager.get_all_tags()
        
        dialog = QDialog()
        dialog.setWindowTitle('标签管理')
        dialog.setFixedSize(500, 400)
        
        layout = QVBoxLayout()
        
        # 标签列表
        tags_list = QListWidget()
        for tag in all_tags:
            item = QListWidgetItem(tag)
            notes_count = len(tag_manager.get_notes_by_tag(tag))
            item.setToolTip(f"包含 {notes_count} 个便签")
            tags_list.addItem(item)
        layout.addWidget(tags_list)
        
        # 按钮
        button_layout = QHBoxLayout()
        delete_btn = QPushButton('删除标签')
        delete_btn.clicked.connect(lambda: self.delete_tag(tags_list.currentItem().text() if tags_list.currentItem() else None))
        button_layout.addStretch()
        button_layout.addWidget(delete_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def delete_tag(self, tag):
        """
        删除标签
        
        Args:
            tag: 标签名称
        """
        if not tag:
            QMessageBox.warning(None, '删除标签', '请选择要删除的标签')
            return
        
        tag_manager = self.get_tag_manager()
        notes_with_tag = tag_manager.get_notes_by_tag(tag)
        
        if notes_with_tag:
            reply = QMessageBox.question(
                None, '删除标签',
                f'此标签已应用到 {len(notes_with_tag)} 个便签，确定要删除吗？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        
        # 从所有便签中移除标签
        for note_id in notes_with_tag:
            tag_manager.remove_tag_from_note(note_id, tag)
        
        QMessageBox.information(None, '删除成功', f'标签 "{tag}" 已删除')
    
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

        # 添加标签管理选项
        tag_action = QAction("标签管理", self.app)
        tag_action.triggered.connect(self.show_tag_management)
        self.tray_menu.addAction(tag_action)

        # 分割线
        self.tray_menu.addSeparator()

        # 创建便签列表的子菜单
        self.notes_menu = QMenu("便签", self.tray_menu)
        self.tray_menu.addMenu(self.notes_menu)

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
            from core.settings import SettingsDialog
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
        from PyQt5.QtCore import QCoreApplication
        QCoreApplication.quit()

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

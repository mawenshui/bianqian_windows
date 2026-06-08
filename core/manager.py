# -*- coding: utf-8 -*-
"""
应用管理器模块

StickyNoteManager 是整个应用的中央控制器，负责：
- 应用生命周期管理（初始化、运行、退出）
- 便签集合管理（创建、加载、删除）
- 系统托盘和菜单
- 全局快捷键协调
- 设置和主题管理
- 与各 feature 模块的集成
"""

import sys
import os
import json
import winreg
from functools import partial

from PyQt5.QtWidgets import (
    QApplication, QMessageBox, QMenu, QAction, QSystemTrayIcon
)
from PyQt5.QtCore import Qt, QCoreApplication, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QStyle

from core.note import StickyNote, NoteLoadWorker
from core.settings import SettingsDialog
from core import get_project_root, get_styles_dir, get_user_data_dir, __version__
from features.search import SearchManager
from features.shortcuts import ShortcutManager
from features.backup import BackupManager
from features.positioning import get_position_manager
from features.reminder import ReminderManager
from features.tag import TagManager
from features.import_export import ImportExportDialog
from features.template import TemplateManager
from features.updater import (
    UpdateChecker, UpdateDownloader, UpdateDialog, UpdateProgressDialog,
    detect_install_type, execute_update
)


class StickyNoteManager:
    """
    桌面便签应用管理器

    单例模式（通常全局只有一个实例），管理所有便签窗口和应用状态。
    """

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # 设置应用图标
        icon_path = os.path.join(get_project_root(), 'icon.png')
        if not os.path.exists(icon_path):
            self.icon = self.app.style().standardIcon(QStyle.SP_DesktopIcon)
        else:
            self.icon = QIcon(icon_path)
        self.app.setWindowIcon(self.icon)

        self.notes = {}
        self.notes_dir = os.path.join(get_user_data_dir(), 'notes')
        os.makedirs(self.notes_dir, exist_ok=True)

        # 加载设置
        self.settings_file = os.path.join(get_user_data_dir(), 'settings.json')
        self.settings = self.load_settings()

        if 'font' not in self.settings:
            self.settings['font'] = {
                'family': '\u5fae\u8f6f\u96c5\u9ed1', 'size': 12,
                'bold': False, 'italic': False
            }
            self.save_settings()

        # 初始化功能模块
        self.search_manager = SearchManager(self)
        self.shortcut_manager = ShortcutManager()
        self.backup_manager = BackupManager(self)
        self.position_manager = get_position_manager()
        self.reminder_manager = ReminderManager(self)
        self.tag_manager = TagManager(self)
        self.template_manager = TemplateManager(self)

        # 注册全局快捷键
        self.setup_global_shortcuts()

        # 设置托盘
        self.setup_tray_icon()

        # 加载已有便签
        self._pending_loaders = []  # 跟踪异步加载器
        self._loaded_note_count = 0
        self._total_note_files = 0
        self.load_notes()

        self.settings_dialog = None

        # 自动检查更新（延迟3秒，避免影响启动速度）
        self._update_checker = None
        self._update_downloader = None
        if self.settings.get('auto_check_update', True):
            QTimer.singleShot(3000, lambda: self.check_for_updates(manual=False))

    # ==================== 全局快捷键 ====================

    def setup_global_shortcuts(self):
        try:
            ok_count = 0
            fail_count = 0
            for combo, action in [
                ('Ctrl+Shift+N', 'add_note'),
                ('Ctrl+Shift+F', 'show_search_dialog'),
                ('Ctrl+Shift+B', 'show_backup_dialog'),
            ]:
                if self.shortcut_manager.register_global_shortcut(combo, action):
                    ok_count += 1
                else:
                    fail_count += 1
            self.shortcut_manager.shortcut_activated.connect(self.handle_shortcut_activated)
            if fail_count >= 2:
                print(f'提示: {fail_count}/{ok_count + fail_count} 个全局快捷键未能注册，应用仍可正常使用（通过托盘菜单操作）')
        except Exception as e:
            print(f'设置全局快捷键时出错: {e}')

    def show_search_dialog(self):
        self.search_manager.show_search_dialog()

    def show_backup_dialog(self):
        self.backup_manager.show_backup_dialog()

    def show_import_export_dialog(self):
        dialog = ImportExportDialog(self)
        dialog.exec_()

    def show_template_dialog(self):
        from features.template import TemplateDialog
        dialog = TemplateDialog(self)
        dialog.exec_()

    def handle_shortcut_activated(self, action_name):
        try:
            if action_name == 'add_note':
                self.add_note()
            elif action_name == 'show_search_dialog':
                self.show_search_dialog()
            elif action_name == 'show_backup_dialog':
                self.show_backup_dialog()
            else:
                print(f"\u672a\u77e5\u7684\u5feb\u6377\u952e\u52a8\u4f5c: {action_name}")
        except Exception as e:
            print(f"\u5904\u7406\u5feb\u6377\u952e\u6fc0\u6d3b\u65f6\u51fa\u9519: {e}")

    # ==================== 系统托盘 ====================

    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self.icon, parent=self.app)
        self.tray_icon.setToolTip("\u684c\u9762\u4fbf\u7b7e\u5e94\u7528")
        self.tray_menu = QMenu()

        add_action = QAction("\u6dfb\u52a0\u4fbf\u7b7e (Ctrl+Shift+N)", self.app)
        add_action.triggered.connect(self.add_note)
        self.tray_menu.addAction(add_action)

        # 从模板创建
        template_action = QAction("\u4ece\u6a21\u677f\u521b\u5efa...", self.app)
        template_action.triggered.connect(self.show_template_dialog)
        self.tray_menu.addAction(template_action)

        search_action = QAction("\u641c\u7d22\u4fbf\u7b7e (Ctrl+Shift+F)", self.app)
        search_action.triggered.connect(self.show_search_dialog)
        self.tray_menu.addAction(search_action)

        backup_action = QAction("备份管理 (Ctrl+Shift+B)", self.app)
        backup_action.triggered.connect(self.show_backup_dialog)
        self.tray_menu.addAction(backup_action)
        
        # 导入导出
        impexp_action = QAction("导入导出", self.app)
        impexp_action.triggered.connect(self.show_import_export_dialog)
        self.tray_menu.addAction(impexp_action)

        self.tray_menu.addSeparator()

        self.notes_menu = QMenu("便签", self.tray_menu)
        self.tray_menu.addMenu(self.notes_menu)
        
        self.tray_menu.addSeparator()
        
        # 标签分组
        self.tags_menu = QMenu("标签分组", self.tray_menu)
        self.tray_menu.addMenu(self.tags_menu)
        
        # 标签管理
        tag_action = QAction("管理标签", self.app)
        tag_action.triggered.connect(self.open_tag_manager)
        self.tray_menu.addAction(tag_action)
        
        self.tray_menu.addSeparator()
        
        self.autostart_action = QAction("开机自启", self.app)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self.check_autostart())
        self.autostart_action.triggered.connect(self.toggle_autostart)
        self.tray_menu.addAction(self.autostart_action)

        settings_action = QAction("设置", self.app)
        settings_action.triggered.connect(self.open_settings)
        self.tray_menu.addAction(settings_action)

        check_update_action = QAction("检查更新", self.app)
        check_update_action.triggered.connect(lambda: self.check_for_updates(manual=True))
        self.tray_menu.addAction(check_update_action)

        help_action = QAction("帮助", self.app)
        help_action.triggered.connect(self.show_help_dialog)
        self.tray_menu.addAction(help_action)
        
        exit_action = QAction("退出", self.app)
        exit_action.triggered.connect(self.exit_application)
        self.tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def update_tray_menu(self):
        self.notes_menu.clear()
        if not self.notes:
            no_notes_action = QAction("暂无便签", self.app)
            no_notes_action.setEnabled(False)
            self.notes_menu.addAction(no_notes_action)
        else:
            for note_id, note in sorted(self.notes.items()):
                note_title = note.note_data.get('title', f'便签 {note_id}')
                note_menu = QMenu(note_title, self.notes_menu)
                open_action = QAction("打开", self.app)
                open_action.triggered.connect(partial(self.open_note, note_id))
                note_menu.addAction(open_action)
                delete_action = QAction("删除", self.app)
                delete_action.triggered.connect(partial(self.delete_note, note_id))
                note_menu.addAction(delete_action)
                self.notes_menu.addMenu(note_menu)
    
        # 按标签分组
        self.tags_menu.clear()
        all_tags = self.tag_manager.get_all_tags()
        if not all_tags:
            no_tag_action = QAction("暂无标签", self.app)
            no_tag_action.setEnabled(False)
            self.tags_menu.addAction(no_tag_action)
        else:
            for tag_name in sorted(all_tags.keys()):
                tag_color = all_tags[tag_name]
                tag_submenu = QMenu(tag_name, self.tags_menu)
                tag_submenu.setStyleSheet(f'QMenu {{ color: {tag_color}; }}')
                tagged_notes = self.tag_manager.get_notes_by_tag(tag_name)
                if tagged_notes:
                    for nid in tagged_notes:
                        note = self.notes.get(nid)
                        if note:
                            title = note.note_data.get('title', f'便签 {nid}')
                            open_action = QAction(title, self.app)
                            open_action.triggered.connect(partial(self.open_note, nid))
                            tag_submenu.addAction(open_action)
                else:
                    empty_action = QAction("(无便签)", self.app)
                    empty_action.setEnabled(False)
                    tag_submenu.addAction(empty_action)
                self.tags_menu.addMenu(tag_submenu)
    
    def open_tag_manager(self):
        """打开标签管理器"""
        from features.tag import TagEditDialog
        dialog = TagEditDialog(self)
        dialog.exec_()
        self.update_tray_menu()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            if self.notes:
                last_note_id = max(self.notes.keys())
                self.open_note(last_note_id)

    # ==================== 便签管理 ====================

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
            # 如果便签处于贴边自动隐藏状态，先恢复
            if note.auto_hidden:
                note._restore_from_auto_hide()
            else:
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
        """
        异步加载所有便签
        
        使用 NoteLoadWorker 在后台线程读取 JSON 文件，
        加载完成后在主线程创建 StickyNote 控件。
        """
        note_files = []
        for filename in os.listdir(self.notes_dir):
            if filename.startswith('note_') and filename.endswith('.json'):
                try:
                    note_id_str = filename.split('_')[1].split('.')[0]
                    note_id = int(note_id_str)
                    if note_id in self.notes:
                        continue
                    file_path = os.path.join(self.notes_dir, filename)
                    note_files.append((note_id, file_path))
                except Exception as e:
                    print(f"\u89e3\u6790\u4fbf\u7b7e\u6587\u4ef6\u540d\u65f6\u51fa\u9519: {e}")

        self._total_note_files = len(note_files)

        if note_files:
            for note_id, file_path in note_files:
                loader = NoteLoadWorker(note_id, file_path)
                loader.loaded.connect(self._on_note_data_loaded)
                loader.failed.connect(self._on_note_load_failed)
                self._pending_loaders.append(loader)
                loader.start()
        else:
            # 没有便签数据文件：创建默认便签并更新托盘菜单
            self.add_note()
            self.update_tray_menu()

    def _on_note_data_loaded(self, note_id: int, data: dict):
        """异步加载完成回调 — 在主线程创建便签控件"""
        try:
            default_theme_css = self.get_default_theme_css()
            new_note = StickyNote(
                note_id, self.notes_dir,
                manager=self,
                theme_css=default_theme_css,
                preloaded_data=data
            )
            new_note.show()
            self.notes[note_id] = new_note
        except Exception as e:
            print(f"\u521b\u5efa\u4fbf\u7b7e {note_id} \u65f6\u51fa\u9519: {e}")
        finally:
            self._loaded_note_count += 1
            self._check_all_loaded()

    def _on_note_load_failed(self, note_id: int, error: str):
        """异步加载失败回调"""
        print(f"\u52a0\u8f7d\u4fbf\u7b7e {note_id} \u5931\u8d25: {error}")
        self._loaded_note_count += 1
        self._check_all_loaded()

    def _check_all_loaded(self):
        """检查是否所有便签都已加载完成"""
        if self._loaded_note_count >= self._total_note_files:
            self.update_tray_menu()
            # 如果异步加载后仍无便签，创建默认便签
            if not self.notes:
                self.add_note()

    def generate_note_id(self):
        existing_ids = set(self.notes.keys())
        note_id = 1
        while note_id in existing_ids:
            note_id += 1
        return note_id

    # ==================== 设置管理 ====================

    def open_settings(self):
        """打开设置对话框（安全模式：每次新建，不使用 WA_DeleteOnClose）"""
        # 如果已有打开的对话框，先关闭它
        if self.settings_dialog is not None:
            try:
                self.settings_dialog.close()
            except Exception:
                pass
            self.settings_dialog = None

        self.settings_dialog = SettingsDialog(self)
        self.settings_dialog.setWindowModality(Qt.NonModal)
        self.settings_dialog.finished.connect(self.on_settings_closed)
        self.settings_dialog.show()

    def on_settings_closed(self, result=None):
        """设置对话框关闭后的清理"""
        if self.settings_dialog is not None:
            try:
                self.settings_dialog.deleteLater()
            except Exception:
                pass
            self.settings_dialog = None

    def show_help_dialog(self):
        """显示完整的帮助使用说明对话框"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout

        dialog = QDialog(None)
        dialog.setWindowTitle('桌面便签 — 完整使用说明')
        dialog.setFixedSize(550, 500)
        dialog.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setHtml('''
<h2>📝 桌面便签 — 完整使用说明</h2>

<h3>📌 基本操作</h3>
<ul>
  <li><b>拖拽移动：</b>按住便签空白区域拖拽可移动位置</li>
  <li><b>缩放调整：</b>鼠标移到便签边缘会变成双向箭头，拖拽即可调整大小</li>
  <li><b>贴边自动隐藏：</b>将便签拖拽到屏幕边缘（紧贴边缘）松手，便签会自动隐藏，仅留下一个标题标签页。鼠标悬停或点击标签页即可恢复便签</li>
  <li><b>关闭/隐藏：</b>点击关闭按钮（×）会将便签隐藏到托盘，不会丢失数据</li>
</ul>

<h3>✏️ 文字格式（需先选中文字）</h3>
<ul>
  <li><b>A+ / A- 按钮：</b>增大或减小选中文字的字体大小</li>
  <li><b>B 按钮：</b>将选中文字设为加粗</li>
  <li><b>I 按钮：</b>将选中文字设为斜体</li>
  <li><b>A(颜色) 按钮：</b>改变选中文字的字体颜色</li>
  <li><b>透明度滑块：</b>调整便签整体透明度</li>
</ul>

<h3>🎨 主题与外观</h3>
<ul>
  <li><b>右键菜单：</b>在便签空白处右键可切换主题、设置字体</li>
  <li><b>始终置顶：</b>勾选"总在最前"可使便签始终显示在其他窗口之上</li>
  <li><b>智能格式化：</b>勾选后粘贴内容时自动格式化</li>
</ul>

<h3>🏷 标签与提醒</h3>
<ul>
  <li><b>标签按钮（🏷）：</b>为便签添加标签，方便分类管理。右键托盘菜单可按标签分组查看</li>
  <li><b>提醒按钮（⏰）：</b>设置定时提醒，到时间后托盘会弹出通知</li>
</ul>

<h3>⌨ 快捷键</h3>
<ul>
  <li><b>Ctrl+Shift+N：</b>全局新建便签</li>
  <li><b>Ctrl+Shift+F：</b>打开便签搜索</li>
  <li><b>Ctrl+Shift+B：</b>打开备份管理</li>
  <li><b>Ctrl+Z / Ctrl+Y：</b>撤销 / 重做</li>
</ul>

<h3>🔍 搜索与备份</h3>
<ul>
  <li><b>搜索便签：</b>托盘菜单 → 搜索便签，可搜索所有便签的标题和内容</li>
  <li><b>备份管理：</b>托盘菜单 → 备份管理，支持导出/恢复备份 ZIP 文件</li>
  <li><b>模板创建：</b>托盘菜单 → 从模板创建，使用预设模板快速创建便签</li>
  <li><b>导入导出：</b>托盘菜单 → 导入导出，支持便签数据的导入和导出</li>
</ul>

<h3>💡 小技巧</h3>
<ul>
  <li>双击托盘图标可快速打开最近使用的便签</li>
  <li>贴边隐藏的便签标签页始终置顶，方便随时找回</li>
  <li>可以在设置中修改默认字体和主题</li>
</ul>
        ''')
        layout.addWidget(help_text)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton('关闭')
        close_btn.setFixedSize(80, 30)
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        dialog.setLayout(layout)
        dialog.exec_()

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                QMessageBox.warning(None, '\u52a0\u8f7d\u8bbe\u7f6e\u9519\u8bef', f'\u65e0\u6cd5\u52a0\u8f7d\u8bbe\u7f6e\u6587\u4ef6: {e}')
                return {'default_theme': "soft_yellow.css"}
        else:
            return {'default_theme': "soft_yellow.css"}

    def save_settings(self):
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            QMessageBox.warning(None, '\u4fdd\u5b58\u8bbe\u7f6e\u9519\u8bef', f'\u65e0\u6cd5\u4fdd\u5b58\u8bbe\u7f6e\u6587\u4ef6: {e}')

    def get_available_themes(self):
        themes = {}
        styles_dir = get_styles_dir()
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
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('/*') and 'Theme Name:' in line:
                        start = line.find('Theme Name:') + len('Theme Name:')
                        end = line.find('*/', start)
                        if end == -1:
                            end = len(line)
                        return line[start:end].strip()
                    elif line and not line.startswith('/*'):
                        break
            return None
        except Exception as e:
            print(f"\u65e0\u6cd5\u4ece {filepath} \u4e2d\u63d0\u53d6\u4e3b\u9898\u540d\u79f0: {e}")
            return None

    def get_theme_name_by_css(self, css_filename):
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
        return self.settings.get('font', {
            'family': '\u5fae\u8f6f\u96c5\u9ed1', 'size': 12,
            'bold': False, 'italic': False
        })

    def set_default_font(self, font_settings):
        self.settings['font'] = font_settings
        self.save_settings()

    def apply_font_to_all_notes(self):
        font_settings = self.get_default_font()
        for note in self.notes.values():
            note.set_font(font_settings)

    # ==================== 开机自启 ====================

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
                    pass
            winreg.CloseKey(key)
            return True
        except Exception as e:
            QMessageBox.warning(None, '\u8bbe\u7f6e\u5f00\u673a\u81ea\u542f\u5931\u8d25', f'\u65e0\u6cd5\u8bbe\u7f6e\u5f00\u673a\u81ea\u542f: {e}')
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
            QMessageBox.warning(None, '\u68c0\u67e5\u5f00\u673a\u81ea\u542f\u5931\u8d25', f'\u65e0\u6cd5\u68c0\u67e5\u5f00\u673a\u81ea\u542f\u72b6\u6001: {e}')
            return False

    def toggle_autostart(self, checked):
        if checked:
            success = self.set_autostart(True)
            if success:
                QMessageBox.information(None, '\u5f00\u673a\u81ea\u542f', '\u5df2\u542f\u7528\u5f00\u673a\u81ea\u542f\u3002')
            else:
                self.autostart_action.setChecked(False)
        else:
            success = self.set_autostart(False)
            if success:
                QMessageBox.information(None, '\u5f00\u673a\u81ea\u542f', '\u5df2\u7981\u7528\u5f00\u673a\u81ea\u542f\u3002')
            else:
                self.autostart_action.setChecked(True)

    # ==================== 保存与更新 ====================

    def save_window_positions(self):
        """保存所有便签的窗口位置到历史记录"""
        try:
            self.position_manager.save_position_history()
        except Exception as e:
            print(f"保存窗口位置时出错: {e}")

    # ==================== 更新流程 ====================

    def check_for_updates(self, manual=False):
        """
        启动版本检查。
        
        Args:
            manual: True = 用户手动触发，会显示"已是最新版本"提示
        """
        self._update_manual = manual
        self._update_checker = UpdateChecker(__version__)
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.no_update.connect(lambda: self._on_no_update(manual))
        self._update_checker.check_failed.connect(self._on_update_check_failed)
        self._update_checker.start()

    def _on_update_available(self, update_info):
        # 检查是否已跳过此版本
        skip_version = self.settings.get('skip_version', '')
        if update_info['tag'] == skip_version:
            if self._update_manual:
                # 手动检查时仍提示
                pass
            else:
                return

        # 显示更新对话框
        dialog = UpdateDialog(update_info, __version__)
        dialog.exec_()

        if dialog.action == 'update':
            self._start_download_update(update_info)
        elif dialog.action == 'skip':
            self.settings['skip_version'] = update_info['tag']
            self.save_settings()
            self._restore_manual_check_btn()
        else:
            # later - 什么都不做
            self._restore_manual_check_btn()

    def _on_no_update(self, manual=False):
        if manual:
            QMessageBox.information(
                None, '检查更新', '当前已是最新版本。'
            )
        self._restore_manual_check_btn()

    def _on_update_check_failed(self, error_msg):
        if hasattr(self, '_update_manual') and self._update_manual:
            QMessageBox.warning(None, '检查更新失败', f'无法检查更新：\n{error_msg}')
        else:
            print(f'[更新] 自动检查失败: {error_msg}')
        self._restore_manual_check_btn()

    def _restore_manual_check_btn(self):
        """恢复设置对话框中的'检查更新'按钮状态"""
        if self.settings_dialog and hasattr(self.settings_dialog, 'check_update_btn'):
            self.settings_dialog.check_update_btn.setEnabled(True)
            self.settings_dialog.check_update_btn.setText("立即检查更新")
            if hasattr(self, '_last_check_status'):
                self.settings_dialog.update_status_label.setText(self._last_check_status)

    def _start_download_update(self, update_info):
        """开始下载更新文件"""
        assets = update_info.get('assets', [])
        if not assets:
            QMessageBox.warning(None, '更新失败', '未找到可下载的更新文件。')
            self._restore_manual_check_btn()
            return

        # 检测安装类型并匹配合适的资产
        install_type = detect_install_type()
        asset = self._match_asset(assets, install_type)
        if not asset:
            QMessageBox.warning(
                None, '更新失败',
                f'未找到适用于当前安装类型（{install_type}）的更新包。'
            )
            self._restore_manual_check_btn()
            return

        download_url = asset.get('browser_download_url', '')
        asset_name = asset.get('name', 'update_package')
        total_size = asset.get('size', 0)
        size_mb = round(total_size / (1024 * 1024), 1)

        # 显示进度对话框
        self._progress_dialog = UpdateProgressDialog(size_mb)
        self._progress_dialog.show()

        # 启动下载
        self._update_downloader = UpdateDownloader(download_url, asset_name, install_type)
        self._update_downloader.progress.connect(self._on_download_progress)
        self._update_downloader.download_finished.connect(self._on_download_finished)
        self._update_downloader.download_failed.connect(self._on_download_failed)
        self._update_downloader.start()

    def _match_asset(self, assets, install_type):
        """根据安装类型匹配最合适的下载资产"""
        if install_type == 'msi':
            for asset in assets:
                name = asset.get('name', '').lower()
                if name.endswith('.msi'):
                    return asset
        # portable 或 source — 使用 .exe
        for asset in assets:
            name = asset.get('name', '').lower()
            if name.endswith('.exe'):
                return asset
        # 回退: 返回第一个资产
        return assets[0] if assets else None

    def _on_download_progress(self, percent):
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.set_progress(percent)

    def _on_download_finished(self, file_path):
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.accept()
            self._progress_dialog = None

        install_type = detect_install_type()

        # 确认后执行更新
        reply = QMessageBox.question(
            None, '下载完成',
            '更新文件已下载完成，是否立即安装？\n\n'
            '应用将自动退出并开始更新。',
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            execute_update(self, file_path, install_type)
        self._restore_manual_check_btn()

    def _on_download_failed(self, error_msg):
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.accept()
            self._progress_dialog = None
        QMessageBox.warning(None, '下载失败', error_msg)
        self._restore_manual_check_btn()

    # ==================== 应用生命周期 ====================

    def exit_application(self):
        try:
            self.shortcut_manager.cleanup()
        except Exception as e:
            print(f"\u6e05\u7406\u5feb\u6377\u952e\u65f6\u51fa\u9519: {e}")
        # 同步保存所有便签后关闭
        for note in list(self.notes.values()):
            note.is_deleted = True
            note._save_timer.stop()
            try:
                note.save_note_sync()
            except Exception as e:
                print(f"\u5173\u95ed\u65f6\u4fdd\u5b58\u4fbf\u7b7e {note.note_id} \u5931\u8d25: {e}")
            note.close()
        self.tray_icon.hide()
        QCoreApplication.quit()

    def run(self):
        sys.exit(self.app.exec_())

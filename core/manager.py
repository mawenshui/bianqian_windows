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
import logging
import winreg
import urllib.request
from functools import partial
from typing import Any, Dict, List, Optional, Tuple, Set

from PyQt5.QtWidgets import (
    QApplication, QMessageBox, QMenu, QAction, QSystemTrayIcon
)
from PyQt5.QtCore import Qt, QCoreApplication, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QStyle

from core.note import StickyNote, NoteLoadWorker
from core.settings import SettingsDialog
from core import get_project_root, get_styles_dir, get_user_data_dir, __version__
from core.config import get_config

logger = logging.getLogger(__name__)
from features.search import SearchManager
from features.shortcuts import ShortcutManager
from features.backup import BackupManager
from features.positioning import get_position_manager
from features.reminder import ReminderManager
from features.tag import TagManager
from features.import_export import ImportExportDialog
from features.template import TemplateManager
from features.linking import NoteLinkManager
from features.plugin_system.registry import PluginRegistry
from features.plugin_system.loader import PluginLoader
from features.plugin_system.api import PluginAPI
from features.updater import (
    UpdateChecker, UpdateDownloader, UpdateDialog, UpdateProgressDialog,
    detect_install_type, execute_update
)


class StickyNoteManager:
    """
    桌面便签应用管理器

    单例模式（通常全局只有一个实例），管理所有便签窗口和应用状态。
    """

    def __init__(self) -> None:
        # 复用已存在的 QApplication 实例（main.py 中已创建），避免重复创建导致 QObject 被销毁
        existing_app = QApplication.instance()
        if existing_app is not None:
            self.app = existing_app
        else:
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
        logger.info(f'便签数据目录: {self.notes_dir}')

        # 加载设置（使用 ConfigManager 统一管理，支持原子写入）
        self.config = get_config()
        self.settings = self.config.get_all()  # 保持向后兼容的快捷访问
        self.settings_file = self.config._settings_file  # 桥接给 feature 模块使用
        
        if 'font' not in self.settings:
            self.config.set('font', {
                'family': '微软雅黑', 'size': 12,
                'bold': False, 'italic': False
            })

        # 初始化核心功能模块（启动必需）
        self.search_manager = SearchManager(self)
        self.shortcut_manager = ShortcutManager()
        self.backup_manager = BackupManager(self)
        self.position_manager = get_position_manager()

        # 延迟加载非关键功能模块（优化启动速度）
        self._reminder_manager = None
        self._tag_manager = None
        self._template_manager = None
        self._link_manager = None
        QTimer.singleShot(500, self._init_deferred_modules)  # 500ms 后加载

        # 插件系统（延迟加载）
        self._plugin_registry = None
        self._plugin_api = None
        self._plugin_loader = None
        QTimer.singleShot(1000, self._init_deferred_plugins)  # 1s 后加载

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

        # 初始化主题文件热加载（延迟1秒）
        QTimer.singleShot(1000, self._init_theme_watcher)

    # ==================== 延迟加载 ====================

    @property
    def reminder_manager(self):
        """延迟加载提醒管理器"""
        if self._reminder_manager is None:
            self._init_deferred_modules()
        return self._reminder_manager

    @property
    def tag_manager(self):
        """延迟加载标签管理器"""
        if self._tag_manager is None:
            self._init_deferred_modules()
        return self._tag_manager

    @property
    def template_manager(self):
        """延迟加载模板管理器"""
        if self._template_manager is None:
            self._init_deferred_modules()
        return self._template_manager

    @property
    def link_manager(self):
        """延迟加载链接管理器"""
        if self._link_manager is None:
            self._init_deferred_modules()
        return self._link_manager

    @property
    def plugin_registry(self):
        """延迟加载插件注册表"""
        if self._plugin_registry is None:
            self._init_deferred_plugins()
        return self._plugin_registry

    @property
    def plugin_api(self):
        """延迟加载插件 API"""
        if self._plugin_api is None:
            self._init_deferred_plugins()
        return self._plugin_api

    @property
    def plugin_loader(self):
        """延迟加载插件加载器"""
        if self._plugin_loader is None:
            self._init_deferred_plugins()
        return self._plugin_loader

    def _init_deferred_modules(self) -> None:
        """初始化延迟加载的功能模块"""
        if self._reminder_manager is None:
            self._reminder_manager = ReminderManager(self)
            logger.debug('延迟初始化: ReminderManager')
        if self._tag_manager is None:
            self._tag_manager = TagManager(self)
            logger.debug('延迟初始化: TagManager')
        if self._template_manager is None:
            self._template_manager = TemplateManager(self)
            logger.debug('延迟初始化: TemplateManager')
        if self._link_manager is None:
            self._link_manager = NoteLinkManager(self.notes_dir)
            logger.debug('延迟初始化: NoteLinkManager')

    def _init_deferred_plugins(self) -> None:
        """初始化延迟加载的插件系统"""
        if self._plugin_registry is None:
            self._plugin_registry = PluginRegistry()
        if self._plugin_api is None:
            self._plugin_api = PluginAPI(self)
        if self._plugin_loader is None:
            plugins_dir = os.path.join(get_project_root(), 'plugins')
            self._plugin_loader = PluginLoader(plugins_dir, self._plugin_api)
            if self.config.get('plugins.enabled', True):
                try:
                    disabled = self.config.get('plugins.disabled', [])
                    loaded = self._plugin_loader.load_all_enabled(
                        [p for p in self._plugin_loader.discover_plugins() if p not in disabled]
                    )
                    for name, instance in loaded.items():
                        self._plugin_registry.register_plugin_instance(name, instance)
                except Exception as e:
                    logger.error(f'加载插件时出错: {e}')
            logger.debug('延迟初始化: 插件系统')

    # ==================== 全局快捷键 ====================

    def setup_global_shortcuts(self) -> None:
        try:
            ok_count = 0
            fail_count = 0
            # 默认快捷键
            default_shortcuts = {
                'add_note': 'Ctrl+Shift+N',
                'show_search_dialog': 'Ctrl+Shift+F',
                'show_backup_dialog': 'Ctrl+Shift+B',
                'show_group_view': 'Ctrl+Shift+G',
            }
            for action, default_combo in default_shortcuts.items():
                # 从配置读取自定义快捷键
                combo = self.config.get(f'shortcuts.{action}', default_combo)
                if self.shortcut_manager.register_global_shortcut(combo, action):
                    ok_count += 1
                else:
                    fail_count += 1
            self.shortcut_manager.shortcut_activated.connect(self.handle_shortcut_activated)
            if fail_count >= 2:
                logger.warning(f'提示: {fail_count}/{ok_count + fail_count} 个全局快捷键未能注册，应用仍可正常使用（通过托盘菜单操作）')
        except Exception as e:
            logger.error(f'设置全局快捷键中出错: {e}')

    def show_search_dialog(self) -> None:
        self.search_manager.show_search_dialog()

    def show_backup_dialog(self) -> None:
        self.backup_manager.show_backup_dialog()

    def show_import_export_dialog(self) -> None:
        dialog = ImportExportDialog(self)
        dialog.exec_()

    def show_template_dialog(self) -> None:
        from features.template import TemplateDialog
        dialog = TemplateDialog(self)
        dialog.exec_()

    def show_group_view(self) -> None:
        """显示便签分组视图"""
        from features.group_view import GroupViewDialog
        dialog = GroupViewDialog(self)
        dialog.exec_()

    def handle_shortcut_activated(self, action_name: str) -> None:
        try:
            if action_name == 'add_note':
                self.add_note()
            elif action_name == 'show_search_dialog':
                self.show_search_dialog()
            elif action_name == 'show_backup_dialog':
                self.show_backup_dialog()
            elif action_name == 'show_group_view':
                self.show_group_view()
            else:
                logger.debug(f'未知的快捷键动作: {action_name}')
        except Exception as e:
            logger.error(f'处理快捷键激活时出错: {e}')

    # ==================== 系统托盘 ====================

    def setup_tray_icon(self) -> None:
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

        # 分组视图
        group_view_action = QAction("分组视图", self.app)
        group_view_action.triggered.connect(self.show_group_view)
        self.tray_menu.addAction(group_view_action)

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
        check_update_action.triggered.connect(lambda: self.check_for_updates(manual=True, source='tray'))
        self.tray_menu.addAction(check_update_action)

        # 插件菜单
        plugins_action = QAction("插件", self.app)
        plugins_action.triggered.connect(self._show_plugins_menu)
        self.tray_menu.addAction(plugins_action)

        # 同步菜单
        sync_action = QAction("云同步", self.app)
        sync_action.triggered.connect(self._show_sync_dialog)
        self.tray_menu.addAction(sync_action)

        # 插件注册的托盘菜单项
        self._plugin_tray_actions = []
        self._refresh_plugin_tray_menu()

        help_action = QAction("帮助", self.app)
        help_action.triggered.connect(self.show_help_dialog)
        self.tray_menu.addAction(help_action)
        
        exit_action = QAction("退出", self.app)
        exit_action.triggered.connect(self.exit_application)
        self.tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def update_tray_menu(self) -> None:
        self.notes_menu.clear()
        if not self.notes:
            no_notes_action = QAction("暂无便签", self.app)
            no_notes_action.setEnabled(False)
            self.notes_menu.addAction(no_notes_action)
        else:
            # 排序：置顶 > 收藏 > 普通（按标题字母）
            sorted_notes = sorted(self.notes.items(), key=lambda x: (
                0 if x[1].note_data.get('pinned', False) else (
                    1 if x[1].note_data.get('favorite', False) else 2
                ),
                x[1].note_data.get('title', f'便签 {x[0]}')
            ))
            last_category = None
            for note_id, note in sorted_notes:
                note_title = note.note_data.get('title', f'便签 {note_id}')
                is_pinned = note.note_data.get('pinned', False)
                is_fav = note.note_data.get('favorite', False)
                current_cat = 'pinned' if is_pinned else ('favorite' if is_fav else 'normal')
                if last_category and current_cat != last_category:
                    self.notes_menu.addSeparator()
                last_category = current_cat
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
    
    def open_tag_manager(self) -> None:
        """打开标签管理器"""
        from features.tag import TagEditDialog
        dialog = TagEditDialog(self)
        dialog.exec_()
        self.update_tray_menu()

    def on_tray_icon_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            if self.notes:
                last_note_id = max(self.notes.keys())
                self.open_note(last_note_id)

    # ==================== 便签管理 ====================

    def add_note(self) -> None:
        note_id = self.generate_note_id()
        logger.info(f'创建新便签 #{note_id}')
        default_theme_css = self.get_default_theme_css()
        new_note = StickyNote(note_id, self.notes_dir, manager=self, theme_css=default_theme_css)
        new_note.show()
        self.notes[note_id] = new_note
        self.update_tray_menu()

    def open_note(self, note_id: int) -> None:
        if note_id in self.notes:
            note = self.notes[note_id]
            # 如果便签处于贴边自动隐藏状态，先恢复
            if note.auto_hidden:
                note._restore_from_auto_hide()
            else:
                note.show()
            note.raise_()
            note.activateWindow()
            # 触发插件钩子 on_note_opened
            if hasattr(self, 'plugin_loader'):
                try:
                    self.plugin_loader.dispatch_event('on_note_opened', note_id, None)
                except Exception as e:
                    logger.debug(f'插件钩子 on_note_opened 失败: {e}')

    def delete_note(self, note_id: int) -> None:
        if note_id in self.notes:
            note = self.notes[note_id]
            note.delete_note()

    def remove_note(self, note_id: int) -> None:
        if note_id in self.notes:
            logger.info(f'移除便签 #{note_id}')
            # 清理链接索引
            if hasattr(self, 'link_manager'):
                try:
                    self.link_manager.remove_note(str(note_id))
                except Exception as e:
                    logger.debug(f'清理链接索引失败: {e}')
            del self.notes[note_id]
            self.update_tray_menu()

    # ==================== 批量操作 ====================

    def batch_delete_notes(self, note_ids: list) -> int:
        """批量删除便签，返回成功删除数量"""
        count = 0
        for note_id in list(note_ids):
            if note_id in self.notes:
                note = self.notes[note_id]
                note.delete_note()
                count += 1
        return count

    def batch_tag_notes(self, note_ids: list, tag_name: str, tag_color: str = None) -> int:
        """批量为便签添加标签"""
        count = 0
        for note_id in note_ids:
            note = self.notes.get(note_id)
            if note:
                tags = note.note_data.get('tags', [])
                if tag_name not in tags:
                    tags.append(tag_name)
                    note.note_data['tags'] = tags
                    note.save_note()
                    count += 1
            else:
                # 未打开的便签，直接修改文件
                note_file = os.path.join(self.notes_dir, f'note_{note_id}.json')
                if os.path.exists(note_file):
                    try:
                        with open(note_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        tags = data.get('tags', [])
                        if tag_name not in tags:
                            tags.append(tag_name)
                            data['tags'] = tags
                            with open(note_file, 'w', encoding='utf-8') as f:
                                json.dump(data, f, ensure_ascii=False, indent=4)
                            count += 1
                    except Exception as e:
                        logger.warning(f'批量标签失败 note_{note_id}: {e}')
        if tag_color and hasattr(self, 'tag_manager'):
            try:
                self.tag_manager.set_tag_color(tag_name, tag_color)
            except Exception as e:
                logger.debug(f'设置标签颜色失败: {e}')
        self.update_tray_menu()
        return count

    def batch_export_notes(self, note_ids: list, export_path: str) -> int:
        """批量导出便签为独立JSON文件"""
        import shutil
        count = 0
        os.makedirs(export_path, exist_ok=True)
        for note_id in note_ids:
            note_file = os.path.join(self.notes_dir, f'note_{note_id}.json')
            if os.path.exists(note_file):
                try:
                    dest = os.path.join(export_path, f'note_{note_id}.json')
                    shutil.copy2(note_file, dest)
                    count += 1
                except Exception as e:
                    logger.warning(f'导出便签 {note_id} 失败: {e}')
        return count

    def toggle_note_pin(self, note_id: int) -> bool:
        """切换便签置顶状态"""
        note = self.notes.get(note_id)
        if note:
            note.toggle_pin()
            return note.is_pinned
        return False

    def toggle_note_favorite(self, note_id: int) -> bool:
        """切换便签收藏状态"""
        note = self.notes.get(note_id)
        if note:
            note.toggle_favorite()
            return note.is_favorite
        return False

    def open_note_by_title(self, title: str) -> None:
        """通过标题查找并打开便签"""
        for note_id, note in self.notes.items():
            note_title = note.note_data.get('title', f'便签 {note_id}')
            if note_title == title:
                self.open_note(note_id)
                return
        logger.warning(f'未找到标题为 "{title}" 的便签')

    def _show_plugins_menu(self) -> None:
        """显示插件菜单对话框"""
        from PyQt5.QtWidgets import (
            QDialog as _QDialog, QVBoxLayout as _VL, QListWidget as _QLW,
            QPushButton as _QBtn, QHBoxLayout as _HL, QLabel as _QLbl
        )
        dialog = _QDialog(None)
        dialog.setWindowTitle('插件管理')
        dialog.setFixedSize(400, 300)
        dialog.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        layout = _VL()
        layout.addWidget(_QLbl('已加载的插件:'))
        list_widget = _QLW()
        if hasattr(self, 'plugin_registry'):
            for name, plugin in self.plugin_registry.list_plugins():
                list_widget.addItem(f'{name} — {plugin.description}')
        if list_widget.count() == 0:
            list_widget.addItem('(无已加载的插件)')
        layout.addWidget(list_widget)
        btn_layout = _HL()
        btn_layout.addStretch()
        close_btn = _QBtn('关闭')
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec_()

    def _show_sync_dialog(self) -> None:
        """显示云同步对话框"""
        try:
            from features.sync_dialog import SyncDialog
            dialog = SyncDialog(self)
            dialog.exec_()
        except Exception as e:
            QMessageBox.warning(None, '云同步', f'打开同步对话框失败: {e}')

    def _refresh_plugin_tray_menu(self) -> None:
        """刷新插件注册的托盘菜单项"""
        # 清除旧的插件动作
        for action in self._plugin_tray_actions:
            self.tray_menu.removeAction(action)
        self._plugin_tray_actions.clear()

        if not hasattr(self, 'plugin_registry'):
            return

        tray_items = self.plugin_registry.get_tray_menu_items()
        if not tray_items:
            return

        help_action = self._find_help_action()

        # 添加分隔线
        sep = self.tray_menu.insertSeparator(help_action)
        self._plugin_tray_actions.append(sep)

        for label, callback in tray_items:
            action = QAction(label, self.app)
            action.triggered.connect(callback)
            self.tray_menu.insertAction(help_action, action)
            self._plugin_tray_actions.append(action)

    def _find_help_action(self):
        """查找帮助菜单项的 QAction"""
        for action in self.tray_menu.actions():
            if action.text() == '帮助':
                return action
        return None

    def _find_help_action_index(self):
        """查找帮助菜单项的索引"""
        actions = self.tray_menu.actions()
        for i, action in enumerate(actions):
            if action.text() == '帮助':
                return i
        return len(actions)

    def load_notes(self) -> None:
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
                    logger.warning(f'解析便签文件名时出错: {e}')

        self._total_note_files = len(note_files)

        if note_files:
            logger.info(f'开始加载 {len(note_files)} 个便签...')
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

    def _on_note_data_loaded(self, note_id: int, data: dict) -> None:
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
            logger.error(f'创建便签 {note_id} 时出错: {e}')
        finally:
            self._loaded_note_count += 1
            self._check_all_loaded()

    def _on_note_load_failed(self, note_id: int, error: str) -> None:
        """异步加载失败回调"""
        logger.warning(f'加载便签 {note_id} 失败: {error}')
        self._loaded_note_count += 1
        self._check_all_loaded()

    def _check_all_loaded(self) -> None:
        """检查是否所有便签都已加载完成"""
        if self._loaded_note_count >= self._total_note_files:
            logger.info(f'便签加载完成: {len(self.notes)} 个便签已就绪')
            self.update_tray_menu()
            # 如果异步加载后仍无便签，创建默认便签
            if not self.notes:
                self.add_note()

    def generate_note_id(self) -> int:
        existing_ids = set(self.notes.keys())
        note_id = 1
        while note_id in existing_ids:
            note_id += 1
        return note_id

    # ==================== 设置管理 ====================

    def open_settings(self) -> None:
        """打开设置对话框（安全模式：每次新建，不使用 WA_DeleteOnClose）"""
        # 如果已有打开的对话框，先关闭它
        if self.settings_dialog is not None:
            try:
                self.settings_dialog.close()
            except Exception as e:
                logger.debug(f'关闭设置对话框失败: {e}')
            self.settings_dialog = None

        self.settings_dialog = SettingsDialog(self)
        self.settings_dialog.setWindowModality(Qt.NonModal)
        self.settings_dialog.finished.connect(self.on_settings_closed)
        self.settings_dialog.show()

    def on_settings_closed(self, result=None) -> None:
        """设置对话框关闭后的清理"""
        if self.settings_dialog is not None:
            try:
                self.settings_dialog.deleteLater()
            except Exception as e:
                logger.debug(f'deleteLater 失败: {e}')
            self.settings_dialog = None

    def show_help_dialog(self) -> None:
        """显示完整的帮助使用说明对话框"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout, QLabel

        dialog = QDialog(None)
        dialog.setWindowTitle('桌面便签 — 完整使用说明')
        dialog.setFixedSize(550, 520)
        dialog.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setHtml(f'''
<h2>📝 桌面便签 — 完整使用说明</h2>
<p style="color:#888; font-size:10pt;">当前版本: v{__version__} | 作者: MaWenshui</p>

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
        version_label = QLabel(f'v{__version__}')
        version_label.setStyleSheet('color: #999; font-size: 9pt;')
        btn_layout.addWidget(version_label)
        btn_layout.addStretch()
        close_btn = QPushButton('关闭')
        close_btn.setFixedSize(80, 30)
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        dialog.setLayout(layout)
        dialog.exec_()

    def load_settings(self) -> Dict[str, Any]:
        """加载设置（委托给 ConfigManager）"""
        return self.config.get_all()
    
    def save_settings(self) -> None:
        """保存设置（委托给 ConfigManager 原子写入）"""
        # 将 self.settings 的变化同步回 config 并保存
        for key, value in self.settings.items():
            self.config.set(key, value, auto_save=False)
        self.config.save()

    def get_available_themes(self) -> Dict[str, str]:
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

    def extract_theme_name_from_css(self, filepath: str) -> Optional[str]:
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
            logger.warning(f'无法从 {filepath} 中提取主题名称: {e}')
            return None

    def get_theme_name_by_css(self, css_filename: str) -> Optional[str]:
        for name, filename in self.get_available_themes().items():
            if filename == css_filename:
                return name
        return None

    def get_default_theme_css(self) -> str:
        return self.settings.get('default_theme', "soft_yellow.css")

    def set_default_theme(self, theme_css: str) -> None:
        self.settings['default_theme'] = theme_css
        self.config.set('default_theme', theme_css)

    def apply_theme_to_all_notes(self) -> None:
        for note in self.notes.values():
            note.set_theme(self.get_default_theme_css())

    def _init_theme_watcher(self) -> None:
        """初始化主题文件热加载监视器"""
        try:
            from features.theme_helper import setup_theme_watcher, invalidate_cache
            styles_dir = get_styles_dir()
            setup_theme_watcher(styles_dir, self._on_theme_files_changed)
        except Exception as e:
            logger.debug(f'初始化主题监视器失败: {e}')

    def _on_theme_files_changed(self) -> None:
        """主题文件变更回调 — 重新应用主题到所有便签"""
        try:
            from features.theme_helper import invalidate_cache
            invalidate_cache()
            self.apply_theme_to_all_notes()
            logger.debug('主题文件已变更，已重新应用到所有便签')
        except Exception as e:
            logger.debug(f'热加载主题失败: {e}')

    def get_default_font(self) -> dict:
        return self.settings.get('font', {
            'family': '\u5fae\u8f6f\u96c5\u9ed1', 'size': 12,
            'bold': False, 'italic': False
        })

    def set_default_font(self, font_settings: dict) -> None:
        self.settings['font'] = font_settings
        self.config.set('font', font_settings)

    def apply_font_to_all_notes(self) -> None:
        font_settings = self.get_default_font()
        for note in self.notes.values():
            note.set_font(font_settings)

    # ==================== 开机自启 ====================

    def set_autostart(self, enable: bool = True) -> bool:
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

    def check_autostart(self) -> bool:
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

    def toggle_autostart(self, checked: bool) -> None:
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

    def save_window_positions(self) -> None:
        """保存所有便签的窗口位置到历史记录"""
        try:
            self.position_manager.save_position_history()
        except Exception as e:
            logger.error(f'保存窗口位置时出错: {e}')

    # ==================== 更新流程 ====================

    def check_for_updates(self, manual: bool = False, source: str = 'auto'):
        """
        启动版本检查。
        
        Args:
            manual: True = 用户手动触发
            source: 'auto' | 'tray' | 'settings' — 触发来源
                    'auto'  → 不显示"已是最新"提示，检查 last_dismissed_version
                    'tray'  → 模态对话框弹窗
                    'settings' → 行内展示结果，不弹模态对话框
        """
        self._update_manual = manual
        self._update_source = source
        self._update_checker = UpdateChecker(__version__)
        self._update_checker.status_update.connect(self._on_check_status_update)
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.no_update.connect(lambda: self._on_no_update(manual))
        self._update_checker.check_failed.connect(self._on_update_check_failed)
        self._update_checker.start()
    
    def cancel_update_check(self) -> None:
        """取消正在进行的版本检查"""
        if self._update_checker and self._update_checker.isRunning():
            self._update_checker.abort()

    def _notify_settings_update_available(self, update_info: dict) -> None:
        """将更新信息转发到设置页面的行内展示区域（不弹模态对话框）"""
        if self.settings_dialog and hasattr(self.settings_dialog, 'show_inline_update_info'):
            self.settings_dialog.show_inline_update_info(update_info, __version__)
        self._restore_manual_check_btn()
    
    def _on_check_status_update(self, status_text: str) -> None:
        """更新检查进度状态 — 转发给设置对话框"""
        if self.settings_dialog and hasattr(self.settings_dialog, 'on_check_status_update'):
            self.settings_dialog.on_check_status_update(status_text)

    def _on_update_available(self, update_info: dict) -> None:
        # 检查是否已跳过此版本
        skip_version = self.settings.get('skip_version', '')
        if update_info['tag'] == skip_version:
            if self._update_manual:
                pass  # 手动检查时仍提示
            else:
                return

        # 自动检查：跳过上次"稍后提醒"过的版本
        source = getattr(self, '_update_source', 'auto')
        if source == 'auto':
            last_dismissed = self.settings.get('last_dismissed_version', '')
            if update_info['tag'] == last_dismissed:
                return

        # 设置页面来源：行内展示结果，不弹模态对话框
        if source == 'settings':
            self._notify_settings_update_available(update_info)
            return

        # 显示更新对话框（托盘菜单手动检查 / 自动检查首次提醒）
        dialog = UpdateDialog(update_info, __version__)
        dialog.exec_()

        if dialog.action == 'update':
            self._start_download_update(update_info)
        elif dialog.action == 'skip':
            self.settings['skip_version'] = update_info['tag']
            self.config.set('skip_version', update_info['tag'])
            self._restore_manual_check_btn()
        else:
            # later — 持久化，自动检查不再提醒此版本
            self.settings['last_dismissed_version'] = update_info['tag']
            self.config.set('last_dismissed_version', update_info['tag'])
            self._restore_manual_check_btn()

    def _on_no_update(self, manual: bool = False) -> None:
        source = getattr(self, '_update_source', 'auto')
        if manual:
            if source == 'settings':
                # 设置页面：仅更新状态标签，不弹窗
                if self.settings_dialog and hasattr(self.settings_dialog, 'update_status_label'):
                    self.settings_dialog.update_status_label.setText("当前已是最新版本 ✓")
                    self.settings_dialog.update_status_label.setStyleSheet("color: #27ae60;")
                    self._last_check_status = "当前已是最新版本 ✓"
            else:
                if self.settings_dialog and hasattr(self.settings_dialog, 'update_status_label'):
                    self.settings_dialog.update_status_label.setText("当前已是最新版本 ✓")
                    self.settings_dialog.update_status_label.setStyleSheet("color: #27ae60;")
                    self._last_check_status = "当前已是最新版本 ✓"
                QMessageBox.information(
                    None, '检查更新', '当前已是最新版本。'
                )
        self._restore_manual_check_btn()

    def _on_update_check_failed(self, error_msg: str) -> None:
        if hasattr(self, '_update_manual') and self._update_manual:
            source = getattr(self, '_update_source', 'tray')
            if self.settings_dialog and hasattr(self.settings_dialog, 'update_status_label'):
                self.settings_dialog.update_status_label.setText(f"检查失败: {error_msg}")
                self.settings_dialog.update_status_label.setStyleSheet("color: #e74c3c;")
                self._last_check_status = f"检查失败: {error_msg}"
            # 设置页面来源不弹错误框（行内已展示），取消操作也不弹
            if '已取消' not in error_msg and source != 'settings':
                QMessageBox.warning(None, '检查更新失败', f'无法检查更新：\n{error_msg}')
        else:
            logger.info(f'[更新] 自动检查失败: {error_msg}')
        self._restore_manual_check_btn()

    def _restore_manual_check_btn(self) -> None:
        """恢复设置对话框中的'检查更新'按钮状态"""
        if self.settings_dialog and hasattr(self.settings_dialog, 'check_update_btn'):
            self.settings_dialog.check_update_btn.setEnabled(True)
            self.settings_dialog.check_update_btn.setText("立即检查更新")
            if hasattr(self.settings_dialog, 'cancel_check_btn'):
                self.settings_dialog.cancel_check_btn.setVisible(False)
                self.settings_dialog.cancel_check_btn.setEnabled(True)
            if hasattr(self.settings_dialog, 'check_progress_bar'):
                self.settings_dialog.check_progress_bar.setVisible(False)
            if hasattr(self, '_last_check_status'):
                self.settings_dialog.update_status_label.setText(self._last_check_status)

    def _start_download_update(self, update_info: dict) -> None:
        """开始下载更新 — 统一下载 portable ZIP"""
        assets = update_info.get('assets', [])
        if not assets:
            QMessageBox.warning(None, '更新失败', '未找到可下载的更新文件。')
            self._restore_manual_check_btn()
            return

        # 检测安装类型并匹配资产
        install_type = detect_install_type()
        zip_asset, msi_asset = self._match_asset(assets, install_type)

        if not zip_asset:
            QMessageBox.warning(
                None, '更新失败',
                f'未找到适用于当前安装类型（{install_type}）的更新包。'
            )
            self._restore_manual_check_btn()
            return

        # 保存 MSI 资产引用和安装类型，供下载完成后使用
        self._pending_msi_asset = msi_asset
        self._pending_install_type = install_type

        download_url = zip_asset.get('browser_download_url', '')
        asset_name = zip_asset.get('name', 'update_package')
        total_size = zip_asset.get('size', 0)
        size_mb = round(total_size / (1024 * 1024), 1)

        # 显示进度对话框
        self._progress_dialog = UpdateProgressDialog(size_mb)
        self._progress_dialog.show()

        # 启动下载
        self._update_downloader = UpdateDownloader(download_url, asset_name)
        self._update_downloader.progress.connect(self._on_download_progress)
        self._update_downloader.status_update.connect(self._on_download_status)
        self._update_downloader.source_changed.connect(self._on_download_source_changed)
        self._update_downloader.download_finished.connect(self._on_download_finished)
        self._update_downloader.download_failed.connect(self._on_download_failed)
        self._update_downloader.start()

    def _match_asset(self, assets: List[dict], install_type: str) -> Tuple[Optional[dict], Optional[dict]]:
        """
        统一下载策略：始终返回 portable ZIP 资产。
        对于 MSI 用户，额外标记 MSI 资产（用于更新注册表）。
        
        Returns:
            (zip_asset, msi_asset_or_none): ZIP 始终优先，MSI 仅 MSI 用户需要
        """
        zip_asset = None
        msi_asset = None

        for asset in assets:
            name = asset.get('name', '').lower()
            if name.endswith('.zip'):
                zip_asset = asset
            elif name.endswith('.msi'):
                msi_asset = asset

        if not zip_asset:
            return (None, None)

        if install_type == 'msi':
            return (zip_asset, msi_asset)
        else:
            return (zip_asset, None)

    def _on_download_progress(self, percent: int) -> None:
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.set_progress(percent)

    def _on_download_status(self, text: str) -> None:
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.set_status(text)

    def _on_download_source_changed(self, source_name: str) -> None:
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.set_source(source_name)

    def _on_download_finished(self, file_path: str) -> None:
        """ZIP 下载完成"""
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.accept()
            self._progress_dialog = None

        install_type = getattr(self, '_pending_install_type', 'portable')
        msi_asset = getattr(self, '_pending_msi_asset', None)

        # MSI 用户：额外下载 MSI 用于更新注册表
        msi_path = None
        if install_type == 'msi' and msi_asset:
            msi_url = msi_asset.get('browser_download_url', '')
            msi_name = msi_asset.get('name', 'update.msi')
            msi_path = self._download_msi_sync(msi_url, msi_name)

        # 确认后执行更新
        reply = QMessageBox.question(
            None, '下载完成',
            '更新文件已下载完成，是否立即安装？\n\n'
            '应用将自动退出并开始更新。',
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            execute_update(self, file_path, install_type, msi_path)
        self._restore_manual_check_btn()

    def _download_msi_sync(self, url: str, name: str) -> Optional[str]:
        """
        同步下载 MSI 文件（体积较小，主线程短时阻塞可接受）。
        
        Returns:
            str: 临时文件路径，失败返回 None
        """
        try:
            import os
            import tempfile
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            temp_path = os.path.join(tempfile.gettempdir(), name)
            with open(temp_path, 'wb') as f:
                f.write(data)
            return temp_path
        except Exception as e:
            logger.warning(f'[更新] MSI 下载失败（将仅更新文件，跳过注册表）: {e}')
            return None

    def _on_download_failed(self, error_msg: str) -> None:
        if hasattr(self, '_progress_dialog') and self._progress_dialog:
            self._progress_dialog.accept()
            self._progress_dialog = None
        # 使用详细错误对话框
        from PyQt5.QtWidgets import QMessageBox
        msg_box = QMessageBox(None)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle('下载更新失败')
        msg_box.setText('更新文件下载失败，所有下载源均无法使用。')
        msg_box.setDetailedText(error_msg)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()
        self._restore_manual_check_btn()

    # ==================== 应用生命周期 ====================

    def exit_application(self) -> None:
        logger.info(f'应用退出，正在保存 {len(self.notes)} 个便签...')
        try:
            self.shortcut_manager.cleanup()
        except Exception as e:
            logger.error(f'清理快捷键时出错: {e}')
        # 卸载插件
        if hasattr(self, 'plugin_loader'):
            try:
                self.plugin_loader.unload_all()
            except Exception as e:
                logger.error(f'卸载插件时出错: {e}')
        # 保存链接索引
        if hasattr(self, 'link_manager'):
            try:
                self.link_manager.save_index()
            except Exception as e:
                logger.error(f'保存链接索引时出错: {e}')
        # 同步保存所有便签后关闭
        for note in list(self.notes.values()):
            note.is_deleted = True
            note._save_timer.stop()
            try:
                note.save_note_sync()
            except Exception as e:
                logger.error(f'关闭时保存便签 {note.note_id} 失败: {e}')
            note.close()
        self.tray_icon.hide()
        QCoreApplication.quit()

    def run(self) -> int:
        sys.exit(self.app.exec_())

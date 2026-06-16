# -*- coding: utf-8 -*-
"""
插件 API — 暴露给插件的安全接口

提供便签 CRUD、UI 操作、配置管理等能力。
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class PluginAPI:
    """暴露给插件的安全 API 接口"""

    def __init__(self, manager):
        """
        Args:
            manager: StickyNoteManager 实例
        """
        self._manager = manager

    # ── 便签操作 ──────────────────────────────────────────

    def get_note_content(self, note_id: int) -> str:
        """获取便签纯文本内容"""
        note = self._manager.notes.get(note_id)
        if note:
            return note.note_data.get('plain_content', '')
        return ''

    def get_note_html(self, note_id: int) -> str:
        """获取便签 HTML 内容"""
        note = self._manager.notes.get(note_id)
        if note:
            return note.note_data.get('content', '')
        return ''

    def get_note_title(self, note_id: int) -> str:
        """获取便签标题"""
        note = self._manager.notes.get(note_id)
        if note:
            return note.note_data.get('title', '')
        return ''

    def get_all_note_ids(self) -> List[int]:
        """获取所有便签 ID 列表"""
        return list(self._manager.notes.keys())

    def get_all_notes(self) -> dict:
        """获取所有便签的 {id: note_data} 字典"""
        return {nid: note.note_data for nid, note in self._manager.notes.items()}

    def create_note(self, title: str = '', content: str = '') -> Optional[int]:
        """创建新便签"""
        try:
            self._manager.add_note()
            # 获取最新创建的便签
            if self._manager.notes:
                note_id = max(self._manager.notes.keys())
                note = self._manager.notes[note_id]
                if title:
                    note.title_edit.setText(title)
                if content:
                    note.text_edit.setPlainText(content)
                note.save_note()
                return note_id
        except Exception as e:
            logger.error(f'插件创建便签失败: {e}')
        return None

    def delete_note(self, note_id: int) -> bool:
        """删除便签"""
        try:
            if note_id in self._manager.notes:
                note = self._manager.notes[note_id]
                note.is_deleted = True
                note.close()
                self._manager.remove_note(note_id)
                return True
        except Exception as e:
            logger.error(f'插件删除便签失败: {e}')
        return False

    # ── UI 操作 ──────────────────────────────────────────

    def show_notification(self, title: str, message: str, duration: int = 3000) -> None:
        """显示系统托盘通知"""
        try:
            from PyQt5.QtWidgets import QSystemTrayIcon
            if self._manager.tray_icon:
                self._manager.tray_icon.showMessage(
                    title, message,
                    QSystemTrayIcon.Information, duration
                )
        except Exception as e:
            logger.error(f'显示通知失败: {e}')

    def add_context_menu_action(self, plugin_name: str, label: str, callback) -> None:
        """注册右键菜单项"""
        if hasattr(self._manager, 'plugin_registry'):
            self._manager.plugin_registry.register(
                plugin_name, 'context_menu', (label, callback)
            )

    def add_toolbar_button(self, plugin_name: str, icon: str, tooltip: str, callback) -> None:
        """注册工具栏按钮"""
        if hasattr(self._manager, 'plugin_registry'):
            self._manager.plugin_registry.register(
                plugin_name, 'toolbar_button',
                {'icon': icon, 'tooltip': tooltip, 'callback': callback}
            )

    def add_tray_menu_item(self, plugin_name: str, label: str, callback) -> None:
        """注册托盘菜单项"""
        if hasattr(self._manager, 'plugin_registry'):
            self._manager.plugin_registry.register(
                plugin_name, 'tray_menu', (label, callback)
            )

    # ── 配置管理 ──────────────────────────────────────────

    def get_plugin_config(self, plugin_name: str) -> dict:
        """获取插件配置"""
        configs = self._manager.config.get('plugins.configs', {})
        return configs.get(plugin_name, {})

    def set_plugin_config(self, plugin_name: str, config: dict) -> None:
        """保存插件配置"""
        configs = self._manager.config.get('plugins.configs', {})
        configs[plugin_name] = config
        self._manager.config.set('plugins.configs', configs)

    def get_current_note_id(self) -> Optional[int]:
        """获取当前活动便签 ID"""
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            focused = app.focusWidget()
            for nid, note in self._manager.notes.items():
                if note.isActiveWindow() or note.isAncestorOf(focused):
                    return nid
        return None

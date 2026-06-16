# -*- coding: utf-8 -*-
"""
插件基类定义

所有插件必须继承 PluginBase，并实现 on_load() 方法。
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class PluginBase(ABC):
    """
    插件基类 — 所有插件必须继承此类

    子类需要定义类属性（name, version, author, description）
    并实现 on_load() 方法。
    """

    # 元信息（子类必须定义）
    name: str = ''
    version: str = '1.0.0'
    author: str = ''
    description: str = ''

    def __init__(self, api):
        """
        Args:
            api: PluginAPI 实例，提供便签操作和 UI 接口
        """
        self.api = api
        self.config: dict = {}

    # ── 生命周期 ──────────────────────────────────────────

    @abstractmethod
    def on_load(self) -> None:
        """插件加载时调用 — 必须实现"""
        ...

    def on_unload(self) -> None:
        """插件卸载时调用 — 可选覆写"""
        pass

    # ── 事件钩子（可选覆写）─────────────────────────────────

    def on_note_opened(self, note_id: int, note_data: dict) -> None:
        """便签打开时触发"""
        pass

    def on_note_saved(self, note_id: int, note_data: dict) -> None:
        """便签保存时触发"""
        pass

    def on_note_closed(self, note_id: int) -> None:
        """便签关闭时触发"""
        pass

    def on_app_started(self) -> None:
        """应用启动完成后触发"""
        pass

    def on_app_closing(self) -> None:
        """应用即将退出时触发"""
        pass

    # ── 注册接口（便捷方法，委托给 api）─────────────────────

    def register_context_menu(self, label: str, callback) -> None:
        """注册右键菜单项"""
        self.api.add_context_menu_action(self.name, label, callback)

    def register_toolbar_button(self, icon: str, tooltip: str, callback) -> None:
        """注册工具栏按钮"""
        self.api.add_toolbar_button(self.name, icon, tooltip, callback)

    def register_tray_menu_item(self, label: str, callback) -> None:
        """注册托盘菜单项"""
        self.api.add_tray_menu_item(self.name, label, callback)

    # ── 数据访问（便捷方法）─────────────────────────────────

    def get_note_content(self, note_id: int) -> str:
        return self.api.get_note_content(note_id)

    def get_all_note_ids(self) -> list:
        return self.api.get_all_note_ids()

    def get_note_title(self, note_id: int) -> str:
        return self.api.get_note_title(note_id)

    def show_notification(self, title: str, message: str) -> None:
        self.api.show_notification(title, message)

    # ── 配置声明（可选覆写）─────────────────────────────────────

    def get_config_fields(self) -> List[Dict[str, Any]]:
        """
        声明插件的可配置字段，用于在设置页面自动生成 UI。

        返回字段列表，每个字段是一个 dict：
        {
            'key': str,           # 配置键名（对应 self.config[key]）
            'label': str,         # 显示标签
            'type': str,          # 'text' | 'int' | 'bool' | 'select'
            'default': Any,       # 默认值
            'min': int,           # int 类型最小值（可选）
            'max': int,           # int 类型最大值（可选）
            'suffix': str,        # int 类型后缀文本（可选，如 '分钟'）
            'options': list,      # select 类型的选项列表（可选）
            'help': str,          # 帮助文本（可选）
            'action': str,        # 特殊按钮标识（可选，如 'auto_locate'）
        }

        子类可覆写此方法声明自己的配置项。
        """
        return []

    def on_config_changed(self, key: str, value: Any) -> None:
        """
        配置变更回调。子类可覆写以响应配置修改。

        Args:
            key: 变更的配置键
            value: 新值
        """
        pass

# -*- coding: utf-8 -*-
"""
插件注册表

集中管理所有插件注册的菜单项、工具栏按钮和事件处理器。
"""

import logging
from typing import Dict, List, Any, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class PluginRegistry:
    """插件注册表"""

    def __init__(self):
        # {plugin_name: {resource_type: [resources]}}
        self._registry: Dict[str, Dict[str, List[Any]]] = defaultdict(lambda: defaultdict(list))
        # {event_name: [(plugin_name, callback)]}
        self._event_handlers: Dict[str, List[Tuple[str, Any]]] = defaultdict(list)
        # {plugin_name: plugin_instance}
        self._plugin_instances: Dict[str, Any] = {}

    def register(self, plugin_name: str, resource_type: str, resource: Any) -> None:
        """注册插件资源"""
        self._registry[plugin_name][resource_type].append(resource)

    def register_event_handler(self, plugin_name: str, event_name: str, callback) -> None:
        """注册事件处理器"""
        self._event_handlers[event_name].append((plugin_name, callback))

    def unregister_all(self, plugin_name: str) -> None:
        """注销插件的所有注册"""
        if plugin_name in self._registry:
            del self._registry[plugin_name]
        for event_name in list(self._event_handlers.keys()):
            self._event_handlers[event_name] = [
                (pn, cb) for pn, cb in self._event_handlers[event_name]
                if pn != plugin_name
            ]

    def get_context_menu_actions(self) -> List[Tuple[str, Any]]:
        """获取所有右键菜单项"""
        result = []
        for plugin_name, resources in self._registry.items():
            for item in resources.get('context_menu', []):
                result.append(item)
        return result

    def get_toolbar_buttons(self) -> List[Dict]:
        """获取所有工具栏按钮"""
        result = []
        for plugin_name, resources in self._registry.items():
            for item in resources.get('toolbar_button', []):
                result.append(item)
        return result

    def get_tray_menu_items(self) -> List[Tuple[str, Any]]:
        """获取所有托盘菜单项"""
        result = []
        for plugin_name, resources in self._registry.items():
            for item in resources.get('tray_menu', []):
                result.append(item)
        return result

    def dispatch_event(self, event_name: str, *args, **kwargs) -> None:
        """分发事件到所有注册的处理器的"""
        for plugin_name, callback in self._event_handlers.get(event_name, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f'插件事件处理失败 [{plugin_name}].{event_name}: {e}')

    def get_loaded_plugins(self) -> List[str]:
        """获取所有已注册的插件名"""
        return list(self._registry.keys())

    def register_plugin_instance(self, plugin_name: str, plugin_instance: Any) -> None:
        """注册插件实例"""
        self._plugin_instances[plugin_name] = plugin_instance
        if plugin_name not in self._registry:
            self._registry[plugin_name] = defaultdict(list)

    def list_plugins(self) -> List[Tuple[str, Any]]:
        """返回 (name, plugin_instance) 列表"""
        result = []
        for name, instance in self._plugin_instances.items():
            result.append((name, instance))
        return result

    def fire_event(self, event_name: str, *args, **kwargs) -> None:
        """分发事件到所有注册的处理器的别名"""
        self.dispatch_event(event_name, *args, **kwargs)

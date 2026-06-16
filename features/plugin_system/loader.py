# -*- coding: utf-8 -*-
"""
插件加载器

扫描 plugins/ 目录，动态加载和卸载插件。
"""

import os
import sys
import importlib
import logging
from typing import Dict, Optional

from features.plugin_system.base import PluginBase

logger = logging.getLogger(__name__)


class PluginLoader:
    """插件加载器"""

    def __init__(self, plugins_dir: str, api):
        self.plugins_dir = plugins_dir
        self.api = api
        self._loaded: Dict[str, PluginBase] = {}

    def discover_plugins(self) -> list:
        """
        扫描 plugins/ 目录，返回可用插件名列表

        插件目录约定:
        plugins/
        ├── plugin_name/
        │   └── __init__.py  # 必须包含 PluginBase 子类
        """
        plugins = []
        if not os.path.exists(self.plugins_dir):
            return plugins

        for item in os.listdir(self.plugins_dir):
            plugin_path = os.path.join(self.plugins_dir, item)
            init_file = os.path.join(plugin_path, '__init__.py')
            if os.path.isdir(plugin_path) and os.path.exists(init_file):
                plugins.append(item)

        return plugins

    def load_plugin(self, plugin_name: str) -> Optional[PluginBase]:
        """
        动态加载单个插件

        Args:
            plugin_name: 插件目录名

        Returns:
            PluginBase 实例，失败返回 None
        """
        if plugin_name in self._loaded:
            logger.warning(f'插件 {plugin_name} 已加载')
            return self._loaded[plugin_name]

        try:
            # 将 plugins/ 目录添加到 sys.path
            if self.plugins_dir not in sys.path:
                sys.path.insert(0, os.path.dirname(self.plugins_dir))

            # 动态导入
            module_name = f'plugins.{plugin_name}'
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)

            # 查找 PluginBase 子类
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                        issubclass(attr, PluginBase) and
                        attr is not PluginBase):
                    plugin_class = attr
                    break

            if plugin_class is None:
                logger.warning(f'插件 {plugin_name} 中未找到 PluginBase 子类')
                return None

            # 实例化并加载
            plugin_instance = plugin_class(self.api)
            plugin_instance.config = self.api.get_plugin_config(plugin_name)
            plugin_instance.on_load()

            self._loaded[plugin_name] = plugin_instance
            logger.info(f'插件加载成功: {plugin_instance.name} v{plugin_instance.version}')
            return plugin_instance

        except Exception as e:
            logger.error(f'加载插件 {plugin_name} 失败: {e}')
            return None

    def unload_plugin(self, plugin_name: str) -> None:
        """卸载插件"""
        if plugin_name in self._loaded:
            try:
                self._loaded[plugin_name].on_unload()
            except Exception as e:
                logger.error(f'卸载插件 {plugin_name} 时出错: {e}')
            del self._loaded[plugin_name]

    def load_all_enabled(self, enabled_list: list = None) -> Dict[str, PluginBase]:
        """
        加载所有已启用的插件

        Args:
            enabled_list: 启用的插件名列表，None 表示加载所有

        Returns:
            {plugin_name: PluginBase} 字典
        """
        available = self.discover_plugins()

        for plugin_name in available:
            if enabled_list is not None and plugin_name not in enabled_list:
                continue
            self.load_plugin(plugin_name)

        return self._loaded

    def unload_all(self) -> None:
        """卸载所有插件"""
        for plugin_name in list(self._loaded.keys()):
            self.unload_plugin(plugin_name)

    def get_loaded_plugins(self) -> Dict[str, PluginBase]:
        """获取所有已加载的插件"""
        return dict(self._loaded)

    def dispatch_event(self, event_name: str, *args, **kwargs) -> None:
        """分发事件到所有已加载的插件"""
        for plugin_name, plugin in self._loaded.items():
            try:
                handler = getattr(plugin, event_name, None)
                if handler and callable(handler):
                    handler(*args, **kwargs)
            except Exception as e:
                logger.error(f'插件事件处理失败 [{plugin_name}].{event_name}: {e}')

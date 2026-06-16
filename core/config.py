# -*- coding: utf-8 -*-
"""
统一配置管理器模块

ConfigManager 单例集中管理所有应用配置项，提供：
- 原子写入（临时文件 + os.replace）
- 嵌套键路径访问（如 "font.family"）
- 类型安全的 getter/setter
- 配置变更信号通知
"""

import os
import json
import logging
import copy
from typing import Any, Optional, Dict
from PyQt5.QtCore import QObject, pyqtSignal

from core import get_user_data_dir

logger = logging.getLogger(__name__)

# 当前配置版本（用于版本迁移）
CONFIG_VERSION = 1

# 默认配置
DEFAULT_SETTINGS: Dict[str, Any] = {
    'config_version': CONFIG_VERSION,
    'default_theme': 'soft_yellow.css',
    'auto_check_update': True,
    'font': {
        'family': '微软雅黑',
        'size': 12,
        'bold': False,
        'italic': False,
    },
    'skip_version': '',
    'last_dismissed_version': '',
    'image': {
        'strategy': 'base64',
        'max_size_kb': 512,
    },
    'security': {
        'master_password_hash': '',
        'master_password_salt': '',
        'require_master_password': False,
    },
    'sync': {
        'enabled': False,
        'provider': 'webdav',
        'webdav': {
            'url': '',
            'username': '',
            'password_encrypted': '',
            'remote_path': '/stickynote/',
        },
        'local_folder': '',
        'auto_sync': False,
        'sync_interval_minutes': 30,
    },
    'plugins': {
        'enabled': True,
        'disabled': [],
        'configs': {},
    },
}


class ConfigManager(QObject):
    """
    统一配置管理器（单例模式）

    提供集中式的配置读写，支持：
    - 嵌套键路径：get('font.size') → 12
    - 原子写入：防止写入中断导致文件损坏
    - 变更信号：config_changed 信号通知监听者
    """

    config_changed = pyqtSignal(str, object)  # (key_path, new_value)

    _instance: Optional['ConfigManager'] = None
    _init_done: bool = False

    def __new__(cls) -> 'ConfigManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 使用类级别标志避免访问 self，因为 QObject 在 super().__init__()
        # 之前访问任何实例属性都会触发 RuntimeError
        if ConfigManager._init_done:
            return
        super().__init__()
        ConfigManager._init_done = True
        self._settings_file = os.path.join(get_user_data_dir(), 'settings.json')
        self._data: Dict[str, Any] = {}
        self.load()

    # ── 文件 I/O ──────────────────────────────────────────

    def load(self) -> Dict[str, Any]:
        """从磁盘加载配置，合并默认值"""
        if os.path.exists(self._settings_file):
            try:
                with open(self._settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    logger.warning('settings.json 格式错误，使用默认配置')
                    self._data = copy.deepcopy(DEFAULT_SETTINGS)
                    return self._data
                # 合并默认值
                self._data = copy.deepcopy(DEFAULT_SETTINGS)
                self._deep_merge(self._data, loaded)
                # 执行版本迁移
                self._data = self._run_migrations(self._data)
                logger.debug('配置加载完成')
            except json.JSONDecodeError as e:
                logger.error(f'settings.json JSON 解析失败: {e}')
                self._data = copy.deepcopy(DEFAULT_SETTINGS)
            except Exception as e:
                logger.error(f'加载配置时出错: {e}')
                self._data = copy.deepcopy(DEFAULT_SETTINGS)
        else:
            self._data = copy.deepcopy(DEFAULT_SETTINGS)
            self.save()
        return self._data

    def save(self) -> None:
        """原子写入配置到磁盘"""
        try:
            tmp_path = self._settings_file + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=4)
            if os.path.exists(self._settings_file):
                os.replace(tmp_path, self._settings_file)
            else:
                os.rename(tmp_path, self._settings_file)
        except Exception as e:
            logger.error(f'保存配置时出错: {e}')
            tmp_path = self._settings_file + '.tmp'
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        """递归合并 override 到 base（原地修改）"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigManager._deep_merge(base[key], value)
            else:
                base[key] = value

    # ── 版本迁移 ─────────────────────────────────────────

    # 迁移链：{from_version: migration_function}
    _migration_chain: Dict[int, callable] = {}

    @classmethod
    def _register_migration(cls, from_version: int, migration_func: callable):
        """
        注册配置版本迁移函数。
        
        Args:
            from_version: 迁移前的版本号
            migration_func: 接收 data dict，原地修改并返回的迁移函数
        """
        cls._migration_chain[from_version] = migration_func

    def _run_migrations(self, data: dict) -> dict:
        """对加载的配置数据执行版本迁移链"""
        current_ver = data.get('config_version', 0)
        while current_ver < CONFIG_VERSION:
            next_ver = current_ver + 1
            migration_func = self._migration_chain.get(current_ver)
            if migration_func:
                try:
                    data = migration_func(data)
                    logger.info(f'配置已从 v{current_ver} 迁移至 v{next_ver}')
                except Exception as e:
                    logger.error(f'配置迁移 v{current_ver} → v{next_ver} 失败: {e}')
                    break
            data['config_version'] = next_ver
            current_ver = next_ver
        return data

    # ── 键路径访问 ────────────────────────────────────────

    def _get_by_path(self, key_path: str) -> Any:
        """通过点分隔路径读取嵌套值"""
        keys = key_path.split('.')
        node = self._data
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                # 尝试从默认值查找
                default_node = DEFAULT_SETTINGS
                for dk in keys:
                    if isinstance(default_node, dict) and dk in default_node:
                        default_node = default_node[dk]
                    else:
                        return None
                return default_node
        return node

    def _set_by_path(self, key_path: str, value: Any) -> None:
        """通过点分隔路径写入嵌套值（自动创建中间节点）"""
        keys = key_path.split('.')
        node = self._data
        for k in keys[:-1]:
            if k not in node or not isinstance(node[k], dict):
                node[k] = {}
            node = node[k]
        node[keys[-1]] = value

    # ── 公共 API ──────────────────────────────────────────

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        读取配置项。

        Args:
            key_path: 点分隔的键路径，如 'font.size'
            default: 默认值

        Returns:
            配置值
        """
        result = self._get_by_path(key_path)
        return result if result is not None else default

    def set(self, key_path: str, value: Any, auto_save: bool = True) -> None:
        """
        写入配置项。

        Args:
            key_path: 点分隔的键路径
            value: 新值
            auto_save: 是否自动持久化（默认 True）
        """
        self._set_by_path(key_path, value)
        if auto_save:
            self.save()
        self.config_changed.emit(key_path, value)

    def get_all(self) -> Dict[str, Any]:
        """获取全部配置的副本"""
        return dict(self._data)

    def _get_default_by_path(self, key_path: str) -> Any:
        """从默认值字典中读取嵌套值"""
        keys = key_path.split('.')
        node = DEFAULT_SETTINGS
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return None
        return node

    def reset(self, key_path: Optional[str] = None) -> None:
        """
        重置配置。

        Args:
            key_path: 指定键路径则仅重置该项，None 则重置全部
        """
        if key_path is None:
            self._data = copy.deepcopy(DEFAULT_SETTINGS)
        else:
            default_val = self._get_default_by_path(key_path)
            if default_val is not None:
                self._set_by_path(key_path, default_val)
        self.save()

    # ── 便捷属性 ──────────────────────────────────────────

    @property
    def default_theme(self) -> str:
        return self.get('default_theme', 'soft_yellow.css')

    @default_theme.setter
    def default_theme(self, value: str) -> None:
        self.set('default_theme', value)

    @property
    def auto_check_update(self) -> bool:
        return self.get('auto_check_update', True)

    @auto_check_update.setter
    def auto_check_update(self, value: bool) -> None:
        self.set('auto_check_update', value)

    @property
    def font_settings(self) -> dict:
        return self.get('font', DEFAULT_SETTINGS['font'])

    @font_settings.setter
    def font_settings(self, value: dict) -> None:
        self.set('font', value)

    @property
    def skip_version(self) -> str:
        return self.get('skip_version', '')

    @skip_version.setter
    def skip_version(self, value: str) -> None:
        self.set('skip_version', value)

    @property
    def last_dismissed_version(self) -> str:
        return self.get('last_dismissed_version', '')

    @last_dismissed_version.setter
    def last_dismissed_version(self, value: str) -> None:
        self.set('last_dismissed_version', value)


# 全局单例访问
_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """获取 ConfigManager 全局单例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager

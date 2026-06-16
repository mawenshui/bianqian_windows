# -*- coding: utf-8 -*-
"""
ConfigManager 单元测试

测试 core/config.py 的配置管理器功能：
- 单例模式
- 嵌套键路径读写
- 原子写入
- 默认值合并
- 配置重置
- 便捷属性访问
"""

import sys
import os
import json
import unittest
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 需要 QApplication 才能导入含有 QObject 的模块
from PyQt5.QtWidgets import QApplication

_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


class TestConfigManager(unittest.TestCase):
    """ConfigManager 核心功能测试"""

    def setUp(self):
        """每个测试前：创建临时配置目录，重置单例"""
        self.temp_dir = tempfile.mkdtemp()
        from core.config import ConfigManager
        # 重置单例状态
        ConfigManager._instance = None
        ConfigManager._init_done = False

    def tearDown(self):
        """清理临时文件"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_config_manager(self):
        """在临时目录中创建 ConfigManager 实例"""
        from core.config import ConfigManager
        ConfigManager._instance = None
        ConfigManager._init_done = False
        with patch('core.config.get_user_data_dir', return_value=self.temp_dir):
            mgr = ConfigManager()
            return mgr

    # ── 单例模式 ──────────────────────────────────────

    def test_singleton_same_instance(self):
        """多次获取应返回同一实例"""
        from core.config import ConfigManager, get_config
        ConfigManager._instance = None
        ConfigManager._init_done = False
        with patch('core.config.get_user_data_dir', return_value=self.temp_dir):
            c1 = ConfigManager()
            c2 = ConfigManager()
        self.assertIs(c1, c2)

    def test_get_config_singleton(self):
        """get_config() 返回 ConfigManager 实例"""
        from core.config import ConfigManager, get_config
        ConfigManager._instance = None
        ConfigManager._init_done = False
        with patch('core.config.get_user_data_dir', return_value=self.temp_dir):
            c = get_config()
        self.assertIsInstance(c, ConfigManager)

    # ── 默认值 ────────────────────────────────────────

    def test_default_theme(self):
        """默认主题应为 soft_yellow.css"""
        mgr = self._create_config_manager()
        self.assertEqual(mgr.default_theme, 'soft_yellow.css')

    def test_default_auto_check_update(self):
        """默认自动更新应为 True"""
        mgr = self._create_config_manager()
        self.assertTrue(mgr.auto_check_update)

    def test_default_font_settings(self):
        """默认字体设置验证"""
        mgr = self._create_config_manager()
        font = mgr.font_settings
        self.assertEqual(font['family'], '微软雅黑')
        self.assertEqual(font['size'], 12)
        self.assertFalse(font['bold'])

    # ── 键路径读写 ────────────────────────────────────

    def test_get_top_level_key(self):
        """读取顶层键"""
        mgr = self._create_config_manager()
        self.assertEqual(mgr.get('default_theme'), 'soft_yellow.css')

    def test_get_nested_key(self):
        """读取嵌套键（font.size）"""
        mgr = self._create_config_manager()
        self.assertEqual(mgr.get('font.size'), 12)

    def test_get_nonexistent_key_returns_default(self):
        """读取不存在的键返回默认值"""
        mgr = self._create_config_manager()
        self.assertIsNone(mgr.get('nonexistent.key'))

    def test_get_nonexistent_with_custom_default(self):
        """读取不存在的键返回自定义默认值"""
        mgr = self._create_config_manager()
        self.assertEqual(mgr.get('nonexistent', 'fallback'), 'fallback')

    def test_set_top_level_key(self):
        """写入顶层键"""
        mgr = self._create_config_manager()
        mgr.set('default_theme', 'fresh_blue.css', auto_save=False)
        self.assertEqual(mgr.get('default_theme'), 'fresh_blue.css')

    def test_set_nested_key(self):
        """写入嵌套键"""
        mgr = self._create_config_manager()
        mgr.set('font.size', 16, auto_save=False)
        self.assertEqual(mgr.get('font.size'), 16)

    def test_set_creates_intermediate_nodes(self):
        """写入深层路径时自动创建中间节点"""
        mgr = self._create_config_manager()
        mgr.set('a.b.c', 'value', auto_save=False)
        self.assertEqual(mgr.get('a.b.c'), 'value')

    # ── 持久化 ────────────────────────────────────────

    def test_save_and_load(self):
        """保存配置后重新加载应保持一致"""
        from core.config import ConfigManager
        mgr = self._create_config_manager()
        mgr.set('default_theme', 'midnight_black.css')
        # 重新加载
        ConfigManager._instance = None
        ConfigManager._init_done = False
        with patch('core.config.get_user_data_dir', return_value=self.temp_dir):
            mgr2 = ConfigManager()
        self.assertEqual(mgr2.default_theme, 'midnight_black.css')

    def test_settings_file_created(self):
        """首次获取配置后应创建 settings.json"""
        mgr = self._create_config_manager()
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, 'settings.json')))

    # ── 默认值合并 ────────────────────────────────────

    def test_missing_keys_use_defaults(self):
        """加载不完整的 JSON 时缺失键使用默认值"""
        # 创建一个只包含部分键的 settings.json
        settings_path = os.path.join(self.temp_dir, 'settings.json')
        partial = {'default_theme': 'warm_pink.css'}
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(partial, f)

        from core.config import ConfigManager
        ConfigManager._instance = None
        ConfigManager._init_done = False
        with patch('core.config.get_user_data_dir', return_value=self.temp_dir):
            mgr = ConfigManager()
        self.assertEqual(mgr.default_theme, 'warm_pink.css')
        self.assertTrue(mgr.auto_check_update)  # 来自默认值

    def test_corrupt_json_falls_back_to_defaults(self):
        """损坏的 JSON 文件回退到默认配置"""
        settings_path = os.path.join(self.temp_dir, 'settings.json')
        with open(settings_path, 'w', encoding='utf-8') as f:
            f.write('this is not json{{{')

        from core.config import ConfigManager
        ConfigManager._instance = None
        ConfigManager._init_done = False
        with patch('core.config.get_user_data_dir', return_value=self.temp_dir):
            mgr = ConfigManager()
        self.assertEqual(mgr.default_theme, 'soft_yellow.css')

    def test_non_dict_json_falls_back(self):
        """非 dict 类型的 JSON 回退到默认配置"""
        settings_path = os.path.join(self.temp_dir, 'settings.json')
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump([1, 2, 3], f)

        from core.config import ConfigManager
        ConfigManager._instance = None
        ConfigManager._init_done = False
        with patch('core.config.get_user_data_dir', return_value=self.temp_dir):
            mgr = ConfigManager()
        self.assertEqual(mgr.default_theme, 'soft_yellow.css')

    # ── 配置重置 ──────────────────────────────────────

    def test_reset_single_key(self):
        """重置单个键恢复默认值"""
        mgr = self._create_config_manager()
        mgr.set('default_theme', 'custom.css', auto_save=False)
        mgr.reset('default_theme')
        self.assertEqual(mgr.default_theme, 'soft_yellow.css')

    def test_reset_all_keys(self):
        """重置全部配置"""
        mgr = self._create_config_manager()
        mgr.set('default_theme', 'custom.css', auto_save=False)
        mgr.set('font.size', 20, auto_save=False)
        mgr.reset()
        self.assertEqual(mgr.default_theme, 'soft_yellow.css')
        self.assertEqual(mgr.get('font.size'), 12)

    # ── 便捷属性 ──────────────────────────────────────

    def test_skip_version_property(self):
        """skip_version 属性读写"""
        mgr = self._create_config_manager()
        mgr.skip_version = 'v2.0.0'
        self.assertEqual(mgr.skip_version, 'v2.0.0')

    def test_last_dismissed_version_property(self):
        """last_dismissed_version 属性读写"""
        mgr = self._create_config_manager()
        mgr.last_dismissed_version = 'v1.9.0'
        self.assertEqual(mgr.last_dismissed_version, 'v1.9.0')

    # ── get_all ──────────────────────────────────────

    def test_get_all_returns_copy(self):
        """get_all() 返回的字典是副本"""
        mgr = self._create_config_manager()
        all1 = mgr.get_all()
        all1['modified'] = True
        all2 = mgr.get_all()
        self.assertNotIn('modified', all2)

    # ── 信号 ──────────────────────────────────────────

    def test_config_changed_signal_emitted(self):
        """set() 应触发 config_changed 信号"""
        mgr = self._create_config_manager()
        signals_received = []

        def on_changed(key, value):
            signals_received.append((key, value))

        mgr.config_changed.connect(on_changed)
        mgr.set('default_theme', 'ocean_teal.css', auto_save=False)

        self.assertEqual(len(signals_received), 1)
        self.assertEqual(signals_received[0], ('default_theme', 'ocean_teal.css'))


if __name__ == '__main__':
    unittest.main(verbosity=2)

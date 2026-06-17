# -*- coding: utf-8 -*-
"""
Manager 更新流程集成测试

测试 manager.py 中自动更新相关的关键逻辑：
- 版本检查信号连接
- 跳过版本逻辑
- 资产匹配
- 设置对话框更新标签页
- 各种边界条件
"""
import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock, PropertyMock, call

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 需要一个假的 QApplication 才能导入 PyQt 相关模块
from PyQt5.QtWidgets import QApplication

# 确保 QApplication 实例存在（测试环境）
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


class TestManagerUpdateHelper(unittest.TestCase):
    """测试 Manager 更新辅助方法（不需要完整 Manager 实例）
    
    注意：_match_asset 当前返回 (zip_asset, msi_asset_or_none) 元组，
    并优先匹配 .zip 资产。
    """

    def test_match_asset_msi_preferred(self):
        """_match_asset: MSI 模式下返回 .zip 为主资产 + .msi 为副资产"""
        from core.manager import StickyNoteManager

        assets = [
            {'name': 'StickyNote.zip', 'browser_download_url': 'https://x.com/e.zip'},
            {'name': 'StickyNote.msi', 'browser_download_url': 'https://x.com/e.msi'},
        ]

        with patch('core.manager.StickyNoteManager.__init__', return_value=None):
            mgr = StickyNoteManager.__new__(StickyNoteManager)

        zip_asset, msi_asset = mgr._match_asset(assets, 'msi')
        self.assertEqual(zip_asset['name'], 'StickyNote.zip')
        self.assertEqual(msi_asset['name'], 'StickyNote.msi')

    def test_match_asset_portable_prefers_zip(self):
        """_match_asset: portable 模式只返回 .zip，不返回 .msi"""
        from core.manager import StickyNoteManager

        assets = [
            {'name': 'StickyNote.msi', 'browser_download_url': 'https://x.com/e.msi'},
            {'name': 'StickyNote.zip', 'browser_download_url': 'https://x.com/e.zip'},
        ]

        with patch('core.manager.StickyNoteManager.__init__', return_value=None):
            mgr = StickyNoteManager.__new__(StickyNoteManager)

        zip_asset, msi_asset = mgr._match_asset(assets, 'portable')
        self.assertEqual(zip_asset['name'], 'StickyNote.zip')
        self.assertIsNone(msi_asset)

    def test_match_asset_only_exe_no_zip(self):
        """_match_asset: 只有 .exe 无 .zip → 返回 (None, None)"""
        from core.manager import StickyNoteManager

        assets = [
            {'name': 'StickyNote.exe', 'browser_download_url': 'https://x.com/e.exe'},
        ]

        with patch('core.manager.StickyNoteManager.__init__', return_value=None):
            mgr = StickyNoteManager.__new__(StickyNoteManager)

        zip_asset, msi_asset = mgr._match_asset(assets, 'msi')
        self.assertIsNone(zip_asset)
        self.assertIsNone(msi_asset)

    def test_match_asset_empty_list(self):
        """_match_asset: 空资产列表返回 (None, None)"""
        from core.manager import StickyNoteManager

        with patch('core.manager.StickyNoteManager.__init__', return_value=None):
            mgr = StickyNoteManager.__new__(StickyNoteManager)

        zip_asset, msi_asset = mgr._match_asset([], 'portable')
        self.assertIsNone(zip_asset)
        self.assertIsNone(msi_asset)

    def test_match_asset_multiple_zip(self):
        """_match_asset: 多个 .zip 时返回最后一个"""
        from core.manager import StickyNoteManager

        assets = [
            {'name': 'StickyNote-x64.zip', 'browser_download_url': 'https://x.com/1'},
            {'name': 'StickyNote-x86.zip', 'browser_download_url': 'https://x.com/2'},
        ]

        with patch('core.manager.StickyNoteManager.__init__', return_value=None):
            mgr = StickyNoteManager.__new__(StickyNoteManager)

        zip_asset, msi_asset = mgr._match_asset(assets, 'portable')
        self.assertEqual(zip_asset['name'], 'StickyNote-x86.zip')


class TestUpdateFlowWithMock(unittest.TestCase):
    """使用 Mock 测试更新流程"""

    def setUp(self):
        from core.manager import StickyNoteManager
        self.update_info = {
            'version': '1.4.0',
            'tag': 'v1.4.0',
            'body': 'Bug fixes',
            'html_url': 'https://github.com/test',
            'assets': [
                {'name': 'StickyNote.exe', 'browser_download_url': 'https://x.com/e.exe',
                 'size': 1024000},
            ],
        }

    def test_check_for_updates_creates_checker(self):
        """check_for_updates 应创建 UpdateChecker 并连接信号"""
        from core.manager import StickyNoteManager
        with patch('core.manager.StickyNoteManager.__init__', return_value=None), \
             patch('core.manager.UpdateChecker') as mock_checker_cls:

            mgr = StickyNoteManager.__new__(StickyNoteManager)
            mgr._update_checker = None
            mgr._update_manual = False

            mock_checker = MagicMock()
            mock_checker_cls.return_value = mock_checker

            mgr.check_for_updates(manual=True)

            mock_checker_cls.assert_called_once()
            self.assertTrue(mock_checker.update_available.connect.called)
            self.assertTrue(mock_checker.start.called)
            self.assertTrue(mgr._update_manual)

    def test_skip_version_auto_check(self):
        """自动检查时跳过已忽略版本"""
        from core.manager import StickyNoteManager
        with patch('core.manager.StickyNoteManager.__init__', return_value=None):
            mgr = StickyNoteManager.__new__(StickyNoteManager)
            mgr.settings = {'skip_version': 'v1.4.0'}
            mgr._update_manual = False
            mgr._start_download_update = MagicMock()
            mgr._restore_manual_check_btn = MagicMock()
            mgr.save_settings = MagicMock()

            # 应该直接 return，不启动下载
            mgr._on_update_available(self.update_info)
            mgr._start_download_update.assert_not_called()

    def test_skip_version_manual_check(self):
        """手动检查时跳过已忽略版本仍应显示对话框"""
        from core.manager import StickyNoteManager
        with patch('core.manager.StickyNoteManager.__init__', return_value=None), \
             patch('core.manager.UpdateDialog') as mock_dialog_cls:

            mgr = StickyNoteManager.__new__(StickyNoteManager)
            mgr.settings = {'skip_version': 'v1.4.0'}
            mgr.settings_dialog = None
            mgr._update_manual = True
            mgr._start_download_update = MagicMock()
            mgr._restore_manual_check_btn = MagicMock()
            mgr.save_settings = MagicMock()
            mgr.config = MagicMock()

            mock_dialog = MagicMock()
            mock_dialog.action = 'later'
            mock_dialog.exec_.return_value = None
            mock_dialog_cls.return_value = mock_dialog

            mgr._on_update_available(self.update_info)

            # 手动检查时仍应创建对话框
            mock_dialog_cls.assert_called_once_with(self.update_info, '1.7.5')

    def test_no_update_manual_shows_message(self):
        """手动检查无更新时显示提示"""
        from core.manager import StickyNoteManager
        with patch('core.manager.StickyNoteManager.__init__', return_value=None), \
             patch('core.manager.QMessageBox.information') as mock_info:

            mgr = StickyNoteManager.__new__(StickyNoteManager)
            mgr.settings_dialog = None
            mgr._update_manual = True
            mgr._restore_manual_check_btn = MagicMock()

            mgr._on_no_update(manual=True)
            mock_info.assert_called_once()

    def test_no_update_auto_silent(self):
        """自动检查无更新时静默"""
        from core.manager import StickyNoteManager
        with patch('core.manager.StickyNoteManager.__init__', return_value=None), \
             patch('core.manager.QMessageBox.information') as mock_info:

            mgr = StickyNoteManager.__new__(StickyNoteManager)
            mgr._update_manual = False
            mgr._restore_manual_check_btn = MagicMock()

            mgr._on_no_update(manual=False)
            mock_info.assert_not_called()

    def test_check_failed_manual_shows_warning(self):
        """手动检查失败显示警告"""
        from core.manager import StickyNoteManager
        with patch('core.manager.StickyNoteManager.__init__', return_value=None), \
             patch('core.manager.QMessageBox.warning') as mock_warn:

            mgr = StickyNoteManager.__new__(StickyNoteManager)
            mgr.settings_dialog = None
            mgr._update_manual = True
            mgr._restore_manual_check_btn = MagicMock()

            mgr._on_update_check_failed('Test error')
            mock_warn.assert_called_once()

    def test_check_failed_auto_logs(self):
        """自动检查失败输出日志"""
        from core.manager import StickyNoteManager
        with patch('core.manager.StickyNoteManager.__init__', return_value=None), \
             patch('core.manager.logger.info') as mock_log:

            mgr = StickyNoteManager.__new__(StickyNoteManager)
            mgr._update_manual = False
            mgr._restore_manual_check_btn = MagicMock()

            mgr._on_update_check_failed('Test error')
            mock_log.assert_called_once()

    def test_start_download_empty_assets(self):
        """无资产时显示错误"""
        from core.manager import StickyNoteManager
        with patch('core.manager.StickyNoteManager.__init__', return_value=None), \
             patch('core.manager.QMessageBox.warning') as mock_warn:

            mgr = StickyNoteManager.__new__(StickyNoteManager)
            mgr._restore_manual_check_btn = MagicMock()

            mgr._start_download_update({'assets': []})
            mock_warn.assert_called_once()

    def test_match_asset_fallback(self):
        """_match_asset: .zip 文件被正确匹配为主资产"""
        from core.manager import StickyNoteManager
        with patch('core.manager.StickyNoteManager.__init__', return_value=None):
            mgr = StickyNoteManager.__new__(StickyNoteManager)
            zip_asset, msi_asset = mgr._match_asset(
                [{'name': 'source.zip', 'url': 'https://x.com/s.zip'}],
                'portable'
            )
            self.assertIsNotNone(zip_asset)
            self.assertEqual(zip_asset['name'], 'source.zip')
            self.assertIsNone(msi_asset)

    def test_match_asset_no_zip_returns_none(self):
        """_match_asset: 无 .zip 资产时返回 (None, None)"""
        from core.manager import StickyNoteManager
        with patch('core.manager.StickyNoteManager.__init__', return_value=None):
            mgr = StickyNoteManager.__new__(StickyNoteManager)
            assets = [
                {'name': 'app.exe', 'url': 'https://x.com/app.exe'},
                {'name': 'app.msi', 'url': 'https://x.com/app.msi'},
            ]
            zip_asset, msi_asset = mgr._match_asset(assets, 'msi')
            self.assertIsNone(zip_asset)
            self.assertIsNone(msi_asset)

    def test_match_asset_zip_only(self):
        """_match_asset: portable 模式下 .zip 被匹配为主资产"""
        from core.manager import StickyNoteManager
        with patch('core.manager.StickyNoteManager.__init__', return_value=None):
            mgr = StickyNoteManager.__new__(StickyNoteManager)
            assets = [
                {'name': 'source.zip', 'url': 'https://x.com/s.zip'},
                {'name': 'app.exe', 'url': 'https://x.com/app.exe'},
            ]
            zip_asset, msi_asset = mgr._match_asset(assets, 'portable')
            self.assertEqual(zip_asset['name'], 'source.zip')
            self.assertIsNone(msi_asset)


class TestSettingsUpdateTab(unittest.TestCase):
    """设置对话框更新标签页测试"""

    def test_update_tab_added(self):
        """验证更新标签页被添加到设置"""
        from core.settings import SettingsDialog
        with patch('core.settings.SettingsDialog.__init__', return_value=None):
            dlg = SettingsDialog.__new__(SettingsDialog)
            dlg.manager = MagicMock()
            dlg.manager.settings = {'auto_check_update': True}
            dlg.manager.save_settings = MagicMock()
            dlg.manager.get_default_theme_css = MagicMock(return_value="soft_yellow.css")
            dlg.manager.get_available_themes = MagicMock(return_value={"柔和黄": "soft_yellow.css"})
            dlg.manager.get_theme_name_by_css = MagicMock(return_value="柔和黄")
            dlg.manager.get_default_font = MagicMock(return_value=None)

        # 验证 setup_update_tab 存在且可调用
        self.assertTrue(hasattr(SettingsDialog, 'setup_update_tab'))
        self.assertTrue(hasattr(SettingsDialog, 'on_auto_update_changed'))
        self.assertTrue(hasattr(SettingsDialog, 'on_manual_check_update'))

    def test_auto_update_checkbox_persists(self):
        """自动更新复选框修改后保存设置"""
        from core.settings import SettingsDialog
        with patch('core.settings.SettingsDialog.__init__', return_value=None):
            dlg = SettingsDialog.__new__(SettingsDialog)
            dlg.manager = MagicMock()
            dlg.manager.settings = {'auto_check_update': True}
            dlg.auto_update_checkbox = MagicMock()
            dlg.auto_update_checkbox.isChecked.return_value = False

            dlg.on_auto_update_changed()

            self.assertFalse(dlg.manager.settings['auto_check_update'])
            dlg.manager.save_settings.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)

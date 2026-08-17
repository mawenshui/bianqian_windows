# -*- coding: utf-8 -*-
"""快捷键设置页的即时应用、推荐与可见诊断测试。"""

import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication, QLabel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.settings import SettingsDialog
from features.shortcuts import get_shortcut_definitions


class _Config:
    def __init__(self):
        self.values = {}

    def set(self, key, value, auto_save=True):
        self.values[key] = value

    def save(self):
        return None


class _Manager:
    def __init__(self, report=None):
        self.config = _Config()
        self.report = report or {'ok': True, 'registered': {}, 'errors': []}
        self.applied = []

    def apply_shortcut_settings(self, values):
        self.applied.append(dict(values))
        return self.report


class TestShortcutSettingsMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _dialog(self, manager=None):
        dialog = SettingsDialog.__new__(SettingsDialog)
        dialog.manager = manager or _Manager()
        dialog._shortcut_definitions = get_shortcut_definitions()
        dialog._shortcut_editors = {
            action: (QLabel(spec['default']), None)
            for action, spec in dialog._shortcut_definitions.items()
        }
        dialog.shortcut_status_icon = QLabel()
        dialog.shortcut_status_label = QLabel()
        return dialog

    def test_recommended_shortcuts_apply_without_other_config(self):
        manager = _Manager()
        dialog = self._dialog(manager)
        manager.config.set('unrelated.value', 'keep')
        with patch('core.settings.QMessageBox.information'):
            self.assertTrue(dialog.apply_recommended_shortcuts())
        self.assertEqual(len(manager.applied), 1)
        self.assertEqual(manager.config.values['unrelated.value'], 'keep')
        self.assertEqual(manager.applied[0]['add_note'], 'Ctrl+Shift+N')

    def test_invalid_or_duplicate_values_are_visible_and_not_applied(self):
        manager = _Manager()
        dialog = self._dialog(manager)
        values = {
            'add_note': 'Ctrl+Shift+N',
            'show_search_dialog': 'Ctrl+Shift+N',
            'show_backup_dialog': 'Ctrl+Shift+B',
            'show_group_view': 'N',
        }
        self.assertFalse(dialog._save_shortcuts(values))
        self.assertEqual(manager.applied, [])
        self.assertIn('快捷键冲突或无效', dialog.shortcut_status_label.text())

    def test_system_failure_is_visible_and_not_reported_as_saved(self):
        manager = _Manager({
            'ok': False,
            'registered': {},
            'errors': [{
                'action': 'add_note',
                'combination': 'Ctrl+Shift+N',
                'reason': 'system_conflict',
            }],
        })
        dialog = self._dialog(manager)
        with patch('core.settings.QMessageBox.information'):
            self.assertFalse(dialog._save_shortcuts())
        self.assertIn('系统中已被其他程序占用', dialog.shortcut_status_label.text())


if __name__ == '__main__':
    unittest.main()

# -*- coding: utf-8 -*-
"""快捷键契约、冲突检测与运行时注册回归测试。"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from features import shortcuts


class TestShortcutContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_canonical_and_duplicate_validation(self):
        self.assertEqual(shortcuts.canonical_shortcut('Ctrl+Shift+N'), 'Ctrl+Shift+N')
        self.assertEqual(shortcuts.canonical_shortcut('N'), '')
        report = shortcuts.validate_shortcut_map({
            'one': 'Ctrl+Shift+N',
            'two': 'Ctrl+Shift+N',
        })
        self.assertFalse(report['ok'])
        self.assertEqual(report['errors'][0]['reason'], 'duplicate')
        self.assertEqual(report['errors'][0]['conflict_with'], 'one')

    def _manager(self):
        fake_con = SimpleNamespace(
            MOD_CONTROL=0x0002,
            MOD_ALT=0x0001,
            MOD_SHIFT=0x0004,
            MOD_WIN=0x0008,
            VK_F1=0x70, VK_F2=0x71, VK_F3=0x72, VK_F4=0x73,
            VK_F5=0x74, VK_F6=0x75, VK_F7=0x76, VK_F8=0x77,
            VK_F9=0x78, VK_F10=0x79, VK_F11=0x7A, VK_F12=0x7B,
            VK_SPACE=0x20, VK_RETURN=0x0D, VK_ESCAPE=0x1B, VK_TAB=0x09,
            VK_BACK=0x08, VK_DELETE=0x2E, VK_INSERT=0x2D, VK_HOME=0x24,
            VK_END=0x23, VK_PRIOR=0x21, VK_NEXT=0x22, VK_UP=0x26,
            VK_DOWN=0x28, VK_LEFT=0x25, VK_RIGHT=0x27,
        )
        return shortcuts.GlobalShortcutManager(), fake_con

    def test_replace_registers_and_cleans_up(self):
        manager, fake_con = self._manager()
        calls = []
        with patch.object(shortcuts, 'WINDOWS_AVAILABLE', True), \
             patch.object(shortcuts, 'win32con', fake_con), \
             patch.object(shortcuts, 'RegisterHotKey', side_effect=lambda *args: calls.append(args) or True), \
             patch.object(shortcuts, 'UnregisterHotKey', side_effect=lambda *args: calls.append(('unregister',) + args)):
            report = manager.replace_shortcuts({
                'add_note': 'Ctrl+Shift+N',
                'show_search_dialog': 'Ctrl+Shift+F',
            })
            self.assertTrue(report['ok'])
            self.assertEqual(manager.get_registered_shortcuts(), {
                'add_note': 'Ctrl+Shift+N',
                'show_search_dialog': 'Ctrl+Shift+F',
            })
            self.assertTrue(manager.clear_shortcuts())
            self.assertEqual(manager.get_registered_shortcuts(), {})
            self.assertTrue(any(item[0] == 'unregister' for item in calls))

    def test_pywin32_void_success_return_is_registered(self):
        manager, fake_con = self._manager()
        with patch.object(shortcuts, 'WINDOWS_AVAILABLE', True), \
             patch.object(shortcuts, 'win32con', fake_con), \
             patch.object(shortcuts, 'RegisterHotKey', return_value=None), \
             patch.object(shortcuts, 'UnregisterHotKey'):
            self.assertTrue(
                manager.register_shortcut('Ctrl+Alt+Shift+F12', 'probe')
            )
            self.assertEqual(
                manager.get_registered_shortcuts(),
                {'probe': 'Ctrl+Alt+Shift+F12'},
            )

    def test_system_registration_failure_returns_reason_and_rolls_back(self):
        manager, fake_con = self._manager()
        with patch.object(shortcuts, 'WINDOWS_AVAILABLE', True), \
             patch.object(shortcuts, 'win32con', fake_con), \
             patch.object(shortcuts, 'RegisterHotKey', side_effect=[True, False]), \
             patch.object(shortcuts, 'UnregisterHotKey'):
            report = manager.replace_shortcuts({
                'add_note': 'Ctrl+Shift+N',
                'show_search_dialog': 'Ctrl+Shift+F',
            })
            self.assertFalse(report['ok'])
            self.assertEqual(report['errors'][0]['reason'], 'registration_failed')
            self.assertEqual(manager.get_registered_shortcuts(), {})

    def test_duplicate_is_rejected_before_os_registration(self):
        manager, _ = self._manager()
        with patch.object(shortcuts, 'WINDOWS_AVAILABLE', True), \
             patch.object(shortcuts, 'RegisterHotKey') as register:
            report = manager.replace_shortcuts({
                'add_note': 'Ctrl+Shift+N',
                'show_search_dialog': 'Ctrl+Shift+N',
            })
            self.assertFalse(report['ok'])
            register.assert_not_called()

    def test_hotkey_signal_and_cleanup(self):
        manager, fake_con = self._manager()
        received = []
        manager.shortcut_activated.connect(received.append)
        with patch.object(shortcuts, 'WINDOWS_AVAILABLE', True), \
             patch.object(shortcuts, 'win32con', fake_con), \
             patch.object(shortcuts, 'RegisterHotKey', return_value=True), \
             patch.object(shortcuts, 'UnregisterHotKey'):
            self.assertTrue(manager.register_shortcut('Ctrl+Shift+N', 'add_note'))
            manager.handle_hotkey_message(1)
            manager.cleanup()
        self.assertEqual(received, ['add_note'])


if __name__ == '__main__':
    unittest.main()

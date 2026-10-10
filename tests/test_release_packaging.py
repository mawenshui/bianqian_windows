# -*- coding: utf-8 -*-
"""发布配置中容易回归的 Windows Installer 路径约束。"""

from pathlib import Path
import unittest


class TestMsiShortcut(unittest.TestCase):
    def test_desktop_shortcut_targets_installed_executable(self):
        source = (Path(__file__).resolve().parents[1] / 'setup.py').read_text(
            encoding='utf-8'
        )
        self.assertIn("('DesktopShortcut', 'DesktopFolder', '便签.lnk'", source)
        self.assertIn("'[#StickyNote.exe]'", source)
        self.assertNotIn("'[TARGETDIR]StickyNote.exe'", source)


if __name__ == '__main__':
    unittest.main()

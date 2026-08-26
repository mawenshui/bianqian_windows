# -*- coding: utf-8 -*-
"""项目目录与开发数据路径测试。"""

import os
import tempfile
import unittest
from unittest.mock import patch

import core


class TestProjectLayout(unittest.TestCase):
    def test_assets_dir_is_below_project_root(self):
        with patch('core.get_project_root', return_value=r'C:\repo\StickyNote'):
            self.assertEqual(
                core.get_assets_dir(),
                os.path.join(r'C:\repo\StickyNote', 'assets'),
            )

    def test_development_data_uses_runtime_directory(self):
        with tempfile.TemporaryDirectory() as project_root:
            with patch('core.get_project_root', return_value=project_root):
                with patch.object(core.sys, 'frozen', False, create=True):
                    data_dir = core.get_user_data_dir()

            self.assertEqual(data_dir, os.path.join(project_root, 'runtime'))
            self.assertTrue(os.path.isdir(data_dir))

    def test_legacy_development_data_is_migrated_without_overwrite(self):
        with tempfile.TemporaryDirectory() as project_root:
            legacy_settings = os.path.join(project_root, 'settings.json')
            with open(legacy_settings, 'w', encoding='utf-8') as stream:
                stream.write('{"source": "legacy"}')

            with patch('core.get_project_root', return_value=project_root):
                with patch.object(core.sys, 'frozen', False, create=True):
                    data_dir = core.get_user_data_dir()

            migrated = os.path.join(data_dir, 'settings.json')
            self.assertFalse(os.path.exists(legacy_settings))
            self.assertTrue(os.path.isfile(migrated))
            with open(migrated, encoding='utf-8') as stream:
                self.assertEqual(stream.read(), '{"source": "legacy"}')


if __name__ == '__main__':
    unittest.main()

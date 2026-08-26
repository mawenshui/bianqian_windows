# -*- coding: utf-8 -*-
"""GitHub Release 工具测试。"""

import json
import unittest
from unittest.mock import MagicMock, patch

from tools.release import create_release


class TestCreateRelease(unittest.TestCase):
    def test_release_files_follow_canonical_layout(self):
        release_dir, notes, assets = create_release.release_files('1.8.0')

        self.assertEqual(release_dir.name, 'v1.8.0')
        self.assertEqual(notes.name, 'RELEASE_NOTES.md')
        self.assertEqual(
            [path.name for path in assets],
            [
                'StickyNote-1.8.0-win64.msi',
                'StickyNote_v1.8.0_Portable.zip',
                'SHA256SUMS.txt',
            ],
        )

    def test_api_serializes_chinese_as_utf8_json(self):
        response = MagicMock()
        response.read.return_value = b'{"id": 1}'
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        with patch('tools.release.create_release.urllib.request.urlopen', return_value=response) as opener:
            result = create_release.api(
                'POST',
                'https://api.github.test/releases',
                'secret',
                {'body': '中文更新说明'},
            )

        request = opener.call_args.args[0]
        self.assertEqual(json.loads(request.data.decode('utf-8'))['body'], '中文更新说明')
        self.assertIn('charset=utf-8', request.headers['Content-type'])
        self.assertEqual(result, {'id': 1})


if __name__ == '__main__':
    unittest.main()

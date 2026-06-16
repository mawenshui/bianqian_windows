# -*- coding: utf-8 -*-
"""
updater 模块自动化测试

覆盖范围：
- parse_version() 版本号解析
- get_download_urls() 双链路 URL 生成
- detect_install_type() 安装类型检测
- UpdateChecker 版本比较逻辑（模拟 API）
- UpdateDownloader 下载流程（模拟网络）
- 边界条件与异常处理
"""
import sys
import os
import json
import unittest
import tempfile
import urllib.error
from unittest.mock import patch, MagicMock, mock_open

# 添加项目根目录到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from features.updater import (
    parse_version,
    get_download_urls,
    detect_install_type,
    UpdateChecker,
    UpdateDownloader,
    GITHUB_DOWNLOAD_TIMEOUT,
    MIRROR_DOWNLOAD_TIMEOUT,
    DOWNLOAD_SOURCES,
    DOWNLOAD_CHUNK_SIZE,
)


class TestParseVersion(unittest.TestCase):
    """版本号解析测试"""

    def test_standard_version(self):
        self.assertEqual(parse_version('1.3.1'), (1, 3, 1))

    def test_version_with_v_prefix(self):
        self.assertEqual(parse_version('v1.3.1'), (1, 3, 1))

    def test_version_two_digits(self):
        self.assertEqual(parse_version('2.0'), (2, 0, 0))

    def test_version_single_digit(self):
        self.assertEqual(parse_version('5'), (5, 0, 0))

    def test_version_with_beta_suffix(self):
        self.assertEqual(parse_version('v2.0-beta'), (2, 0, 0))

    def test_version_with_spaces(self):
        self.assertEqual(parse_version('  v1.5.2  '), (1, 5, 2))

    def test_version_empty_string(self):
        self.assertEqual(parse_version(''), (0, 0, 0))

    def test_version_none(self):
        self.assertEqual(parse_version(None), (0, 0, 0))

    def test_version_invalid(self):
        self.assertEqual(parse_version('abc'), (0, 0, 0))

    def test_version_comparison(self):
        """验证版本比较正确性"""
        self.assertTrue(parse_version('2.0.0') > parse_version('1.9.9'))
        self.assertTrue(parse_version('1.10.0') > parse_version('1.9.9'))
        self.assertTrue(parse_version('1.3.2') > parse_version('1.3.1'))
        self.assertTrue(parse_version('1.3.10') > parse_version('1.3.9'))
        self.assertFalse(parse_version('1.3.1') > parse_version('1.3.1'))
        self.assertFalse(parse_version('1.2.0') > parse_version('1.3.0'))

    def test_max_version_values(self):
        """大版本号解析"""
        self.assertEqual(parse_version('v999.888.777'), (999, 888, 777))


class TestGetDownloadUrls(unittest.TestCase):
    """双链路 URL 生成测试"""

    def setUp(self):
        self.original_url = (
            'https://github.com/mawenshui/bianqian_windows/'
            'releases/download/v1.4.0/StickyNote.exe'
        )

    def test_returns_list_of_tuples(self):
        urls = get_download_urls(self.original_url)
        self.assertIsInstance(urls, list)
        self.assertEqual(len(urls), len(DOWNLOAD_SOURCES))
        for name, url, timeout in urls:
            self.assertIsInstance(name, str)
            self.assertIsInstance(url, str)
            self.assertIsInstance(timeout, (int, float))

    def test_first_url_is_original(self):
        urls = get_download_urls(self.original_url)
        self.assertEqual(urls[0][0], 'GitHub 官方源')
        self.assertEqual(urls[0][1], self.original_url)

    def test_first_url_timeout(self):
        urls = get_download_urls(self.original_url)
        self.assertEqual(urls[0][2], GITHUB_DOWNLOAD_TIMEOUT)

    def test_second_url_is_mirror(self):
        urls = get_download_urls(self.original_url)
        # 第二个源应该是第一个镜像
        mirror_name, mirror_prefix, mirror_timeout = DOWNLOAD_SOURCES[1]
        expected_url = mirror_prefix.replace('{url}', self.original_url)
        self.assertEqual(urls[1][0], mirror_name)
        self.assertEqual(urls[1][1], expected_url)

    def test_second_url_timeout(self):
        urls = get_download_urls(self.original_url)
        self.assertEqual(urls[1][2], MIRROR_DOWNLOAD_TIMEOUT)

    def test_mirror_timeout_longer_than_github(self):
        urls = get_download_urls(self.original_url)
        self.assertGreater(urls[1][2], urls[0][2])

    def test_url_with_special_characters(self):
        url = 'https://github.com/repo/releases/download/v1.0/file (1).exe'
        urls = get_download_urls(url)
        self.assertEqual(len(urls), len(DOWNLOAD_SOURCES))


class TestDetectInstallType(unittest.TestCase):
    """安装类型检测测试"""

    def test_source_mode(self):
        """开发模式下应返回 'source'"""
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(detect_install_type(), 'source')

    def test_portable_mode(self):
        """便携版不在 Program Files 中"""
        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, 'executable', 'D:\\Apps\\StickyNote\\StickyNote.exe'):
                self.assertEqual(detect_install_type(), 'portable')

    def test_msi_mode_program_files(self):
        """MSI 安装在 Program Files"""
        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, 'executable',
                              'C:\\Program Files\\StickyNote\\StickyNote.exe'):
                self.assertEqual(detect_install_type(), 'msi')

    def test_msi_mode_program_files_x86(self):
        """MSI 安装在 Program Files (x86)"""
        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, 'executable',
                              'C:\\Program Files (x86)\\StickyNote\\StickyNote.exe'):
                self.assertEqual(detect_install_type(), 'msi')

    def test_case_insensitive(self):
        """路径匹配应忽略大小写"""
        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, 'executable',
                              'c:\\program files\\stickynote\\stickynote.exe'):
                self.assertEqual(detect_install_type(), 'msi')


class TestUpdateChecker(unittest.TestCase):
    """版本检查器测试"""

    def setUp(self):
        self.current_version = '1.3.1'

    def _create_mock_response(self, tag_name='v1.3.1', body='test body'):
        """创建模拟的 GitHub API 响应"""
        mock_resp = MagicMock()
        response_data = json.dumps({
            'tag_name': tag_name,
            'body': body,
            'html_url': 'https://github.com/test/releases/tag/' + tag_name,
            'assets': [{'name': 'StickyNote.exe', 'browser_download_url': 'https://example.com'}]
        }).encode()
        mock_resp.read.return_value = response_data
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        return mock_resp

    @patch('features.updater.urllib.request.urlopen')
    def test_update_available(self, mock_urlopen):
        """检测到新版本时发射 update_available 信号"""
        mock_urlopen.return_value = self._create_mock_response('v2.0.0')
        checker = UpdateChecker(self.current_version)
        signals_received = []

        checker.update_available.connect(lambda info: signals_received.append(('available', info)))
        checker.no_update.connect(lambda: signals_received.append(('no_update',)))
        checker.run()
        checker.wait()

        self.assertEqual(len(signals_received), 1)
        self.assertEqual(signals_received[0][0], 'available')
        self.assertEqual(signals_received[0][1]['version'], '2.0.0')

    @patch('features.updater.urllib.request.urlopen')
    def test_no_update_same_version(self, mock_urlopen):
        """版本相同时发射 no_update 信号"""
        mock_urlopen.return_value = self._create_mock_response('v1.3.1')
        checker = UpdateChecker(self.current_version)
        signals_received = []

        checker.no_update.connect(lambda: signals_received.append(True))
        checker.run()
        checker.wait()

        self.assertEqual(len(signals_received), 1)

    @patch('features.updater.urllib.request.urlopen')
    def test_no_update_older_version(self, mock_urlopen):
        """最新版低于当前版时发射 no_update"""
        mock_urlopen.return_value = self._create_mock_response('v1.2.0')
        checker = UpdateChecker(self.current_version)
        signals_received = []

        checker.no_update.connect(lambda: signals_received.append(True))
        checker.run()
        checker.wait()

        self.assertEqual(len(signals_received), 1)

    @patch('features.updater.urllib.request.urlopen')
    def test_no_update_newer_minor(self, mock_urlopen):
        """检测到次版本更新"""
        mock_urlopen.return_value = self._create_mock_response('v1.3.2')
        checker = UpdateChecker(self.current_version)
        signals_received = []

        checker.update_available.connect(lambda info: signals_received.append(info))
        checker.run()
        checker.wait()

        self.assertEqual(len(signals_received), 1)
        self.assertEqual(signals_received[0]['version'], '1.3.2')

    @patch('features.updater.urllib.request.urlopen')
    def test_http_error_403(self, mock_urlopen):
        """HTTP 403 错误处理"""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'url', 403, 'Forbidden', {}, None
        )
        checker = UpdateChecker(self.current_version)
        signals_received = []

        checker.check_failed.connect(lambda msg: signals_received.append(msg))
        checker.run()
        checker.wait()

        self.assertEqual(len(signals_received), 1)
        self.assertIn('403', signals_received[0])

    @patch('features.updater.urllib.request.urlopen')
    def test_json_decode_error(self, mock_urlopen):
        """JSON 解析错误处理"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'invalid json{{{'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        checker = UpdateChecker(self.current_version)
        signals_received = []

        checker.check_failed.connect(lambda msg: signals_received.append(msg))
        checker.run()
        checker.wait()

        self.assertEqual(len(signals_received), 1)
        self.assertIn('格式异常', signals_received[0])

    @patch('features.updater.urllib.request.urlopen')
    def test_empty_tag_name(self, mock_urlopen):
        """空 tag_name 时发射 no_update"""
        mock_urlopen.return_value = self._create_mock_response('')
        checker = UpdateChecker(self.current_version)
        signals_received = []

        checker.no_update.connect(lambda: signals_received.append(True))
        checker.run()
        checker.wait()

        self.assertEqual(len(signals_received), 1)


class TestUpdateDownloader(unittest.TestCase):
    """下载器测试"""

    def setUp(self):
        self.test_url = 'https://github.com/test/releases/download/v1.0/test.exe'
        self.asset_name = 'test.exe'

    @patch('features.updater.test_connection', return_value=(True, ''))
    @patch('features.updater.urllib.request.urlopen')
    def test_successful_download(self, mock_urlopen, mock_test_conn):
        """成功下载文件"""
        test_data = b'x' * (DOWNLOAD_CHUNK_SIZE + 100)  # 略大于一个 chunk
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.headers = {'Content-Length': str(len(test_data))}

        # 模拟分块读取
        def read_side_effect(size=-1):
            read_side_effect.called += 1
            if read_side_effect.called == 1:
                return test_data[:DOWNLOAD_CHUNK_SIZE]
            elif read_side_effect.called == 2:
                return test_data[DOWNLOAD_CHUNK_SIZE:]
            else:
                return b''

        read_side_effect.called = 0
        mock_resp.read.side_effect = read_side_effect
        mock_urlopen.return_value = mock_resp

        downloader = UpdateDownloader(self.test_url, self.asset_name)
        results = []
        progress_values = []

        downloader.download_finished.connect(lambda path: results.append(('done', path)))
        downloader.download_failed.connect(lambda msg: results.append(('fail', msg)))
        downloader.progress.connect(progress_values.append)
        downloader.run()
        downloader.wait()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], 'done')
        self.assertTrue(os.path.exists(results[0][1]))
        self.assertTrue(os.path.basename(results[0][1]), self.asset_name)

        # 验证文件内容
        with open(results[0][1], 'rb') as f:
            self.assertEqual(f.read(), test_data)

        # 清理
        import shutil
        shutil.rmtree(os.path.dirname(results[0][1]), ignore_errors=True)

    @patch('features.updater.test_connection', return_value=(True, ''))
    @patch('features.updater.urllib.request.urlopen')
    def test_progress_signals(self, mock_urlopen, mock_test_conn):
        """验证进度信号"""
        test_data = b'x' * DOWNLOAD_CHUNK_SIZE * 3
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.headers = {'Content-Length': str(len(test_data))}

        chunk_count = [0]

        def read_side_effect(size=-1):
            if chunk_count[0] >= 3:
                return b''
            chunk_count[0] += 1
            return test_data[:DOWNLOAD_CHUNK_SIZE]

        mock_resp.read.side_effect = read_side_effect
        mock_urlopen.return_value = mock_resp

        downloader = UpdateDownloader(self.test_url, self.asset_name)
        progress_values = []
        done = []

        downloader.progress.connect(progress_values.append)
        downloader.download_finished.connect(lambda p: done.append(p))
        downloader.run()
        downloader.wait()

        self.assertGreater(len(progress_values), 0)
        self.assertEqual(progress_values[-1], 100)

        # 清理
        if done:
            import shutil
            shutil.rmtree(os.path.dirname(done[0]), ignore_errors=True)

    @patch('features.updater.test_connection', return_value=(True, ''))
    @patch('features.updater.urllib.request.urlopen')
    def test_download_fallback_to_mirror(self, mock_urlopen, mock_test_conn):
        """主链接失败后切换到镜像"""
        call_urls = []
        mirror_prefix = DOWNLOAD_SOURCES[1][1]  # 第一个镜像的URL前缀

        def urlopen_side_effect(req, **kwargs):
            call_urls.append(req.full_url if hasattr(req, 'full_url') else str(req))
            # 连接测试 + 下载都会调用 urlopen
            url_str = req.full_url if hasattr(req, 'full_url') else str(req)
            if mirror_prefix.split('/')[2] not in url_str and 'github.com' in url_str:
                raise urllib.error.URLError('GitHub 连接超时')
            # 镜像成功
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.headers = {'Content-Length': '10'}
            mock_resp.read.side_effect = [b'1234567890', b'']
            return mock_resp

        mock_urlopen.side_effect = urlopen_side_effect

        downloader = UpdateDownloader(self.test_url, self.asset_name)
        results = []

        downloader.download_finished.connect(lambda p: results.append(('done', p)))
        downloader.download_failed.connect(lambda m: results.append(('fail', m)))
        downloader.run()
        downloader.wait()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], 'done')

        # 清理
        import shutil
        shutil.rmtree(os.path.dirname(results[0][1]), ignore_errors=True)

    @patch('features.updater.test_connection', return_value=(False, '连接超时'))
    @patch('features.updater.urllib.request.urlopen')
    def test_both_urls_fail(self, mock_urlopen, mock_test_conn):
        """两个链接都失败"""
        mock_urlopen.side_effect = urllib.error.URLError('所有源均不可用')

        downloader = UpdateDownloader(self.test_url, self.asset_name)
        results = []

        downloader.download_failed.connect(lambda msg: results.append(msg))
        downloader.run()
        downloader.wait()

        self.assertEqual(len(results), 1)
        self.assertIn('所有下载源均不可用', results[0])

    @patch('features.updater.test_connection', return_value=(True, ''))
    @patch('features.updater.urllib.request.urlopen')
    def test_abort_download(self, mock_urlopen, mock_test_conn):
        """中断下载"""
        test_data = b'x' * DOWNLOAD_CHUNK_SIZE * 10
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.headers = {'Content-Length': str(len(test_data))}

        # 下载中断
        downloader = UpdateDownloader(self.test_url, self.asset_name)
        mock_resp.read.side_effect = [test_data[:DOWNLOAD_CHUNK_SIZE]] + [b''] * 10

        results = []
        downloader.download_finished.connect(lambda p: results.append(('done', p)))
        downloader.download_failed.connect(lambda m: results.append(('fail', m)))

        # 启动后立即中止
        downloader.abort()
        downloader.run()
        downloader.wait()

        # 被中止时不应发射任何信号
        self.assertEqual(len(results), 0)

    @patch('features.updater.test_connection')
    @patch('features.updater.urllib.request.urlopen')
    def test_zero_size_file(self, mock_urlopen, mock_test_conn):
        """下载空文件"""
        mock_test_conn.return_value = (True, '')  # 连接测试通过
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.headers = {'Content-Length': '0'}
        mock_resp.read.return_value = b''
        mock_urlopen.return_value = mock_resp

        downloader = UpdateDownloader(self.test_url, self.asset_name)
        results = []

        downloader.download_finished.connect(lambda p: results.append(('done', p)))
        downloader.download_failed.connect(lambda m: results.append(('fail', m)))
        downloader.run()
        downloader.wait()

        # 空文件应该触发失败（下载内容为空）
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], 'fail')


class TestEdgeCases(unittest.TestCase):
    """边界条件测试"""

    def test_parse_version_very_long(self):
        """超长版本号"""
        result = parse_version('v1.2.3.4.5.6.7.8.9')
        self.assertEqual(result, (1, 2, 3))

    def test_parse_version_negative(self):
        """负号被移除，得到正数版本（版本号不存在负数）"""
        result = parse_version('-1.0.0')
        self.assertEqual(result, (1, 0, 0))

    def test_get_download_urls_empty_string(self):
        """空 URL"""
        urls = get_download_urls('')
        self.assertEqual(len(urls), len(DOWNLOAD_SOURCES))
        # 第一个应该是 GitHub 官方源
        self.assertEqual(urls[0][0], 'GitHub 官方源')

    def test_parse_version_with_pre_release(self):
        """预发布版本"""
        result = parse_version('v2.0.0-rc.1')
        self.assertEqual(result, (2, 0, 0))


if __name__ == '__main__':
    unittest.main(verbosity=2)

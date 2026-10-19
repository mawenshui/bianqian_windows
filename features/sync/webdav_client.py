# -*- coding: utf-8 -*-
"""
WebDAV 同步客户端

支持坚果云、Nextcloud 等 WebDAV 服务。
"""

import os
import logging
import hashlib
import tempfile
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from webdav3.client import Client as WebdavClient
    HAS_WEBDAV = True
except ImportError:
    HAS_WEBDAV = False
    logger.warning('webdavclient3 库未安装，WebDAV 同步不可用')


class WebDAVClient:
    """WebDAV 客户端封装"""

    def __init__(self, url: str, username: str, password: str, remote_path: str = '/StickyNote/'):
        self.url = url
        self.username = username
        self.password = password
        self.remote_path = remote_path.rstrip('/') + '/'
        self._client = None
        self._hash_cache = {}

    def _ensure_client(self):
        if not HAS_WEBDAV:
            raise RuntimeError('webdavclient3 库未安装')
        if self._client is None:
            options = {
                'webdav_hostname': self.url,
                'webdav_login': self.username,
                'webdav_password': self.password,
            }
            self._client = WebdavClient(options)
        return self._client

    def check_connection(self) -> bool:
        """检查 WebDAV 连接"""
        try:
            client = self._ensure_client()
            client.check(self.remote_path)
            return True
        except Exception:
            try:
                client = self._ensure_client()
                client.mkdir(self.remote_path)
                return True
            except Exception as e:
                logger.error(f'WebDAV 连接失败: {e}')
                return False

    def list_files(self) -> List[str]:
        """列出远端目录中的文件"""
        try:
            client = self._ensure_client()
            files = client.list(self.remote_path)
            return [f for f in files if f.endswith('.json') and f.startswith('note_')]
        except Exception as e:
            logger.error(f'列出远端文件失败: {e}')
            return []

    def upload_file(self, local_path: str, filename: str) -> bool:
        """上传文件到远端"""
        try:
            client = self._ensure_client()
            remote = self.remote_path + filename
            client.upload(remote, local_path)
            return True
        except Exception as e:
            logger.error(f'上传文件失败: {filename} - {e}')
            return False

    def download_file(self, filename: str, local_path: str) -> bool:
        """从远端下载文件"""
        try:
            client = self._ensure_client()
            remote = self.remote_path + filename
            client.download(remote, local_path)
            return True
        except Exception as e:
            logger.error(f'下载文件失败: {filename} - {e}')
            return False

    def delete_file(self, filename: str) -> bool:
        """删除远端文件"""
        try:
            client = self._ensure_client()
            remote = self.remote_path + filename
            client.clean(remote)
            return True
        except Exception as e:
            logger.error(f'删除远端文件失败: {filename} - {e}')
            return False

    def get_file_hashes(self) -> Dict[str, str]:
        """Return real SHA-256 values; ETag only avoids unchanged downloads."""
        result = {}
        try:
            client = self._ensure_client()
            files = client.list(self.remote_path)
            for item in files:
                filename = os.path.basename(str(item).rstrip('/'))
                if not re.fullmatch(r'note_[1-9]\d*\.json', filename):
                    continue
                remote = self.remote_path + filename
                try:
                    info = client.info(remote)
                    etag = str(info.get('etag', ''))
                except Exception:
                    etag = ''
                cached = self._hash_cache.get(filename)
                if etag and cached and cached[0] == etag:
                    result[filename] = cached[1]
                    continue
                descriptor, temporary = tempfile.mkstemp(prefix='stickynote_webdav_', suffix='.tmp')
                os.close(descriptor)
                try:
                    if client.download(remote, temporary) is False:
                        raise OSError(f'远端下载失败: {filename}')
                    digest = hashlib.sha256()
                    with open(temporary, 'rb') as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                            digest.update(chunk)
                    result[filename] = digest.hexdigest()
                    if etag:
                        self._hash_cache[filename] = (etag, result[filename])
                finally:
                    if os.path.exists(temporary):
                        os.remove(temporary)
        except Exception as e:
            logger.error(f'获取远端文件信息失败: {e}')
            raise OSError(f'远端文件列表或内容读取失败: {e}') from e
        return result

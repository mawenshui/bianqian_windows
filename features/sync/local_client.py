# -*- coding: utf-8 -*-
"""
本地文件夹同步客户端

用于将便签数据镜像到本地同步文件夹（如 OneDrive 同步目录）。
"""

import os
import shutil
import hashlib
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class LocalSyncClient:
    """本地文件夹同步客户端"""

    def __init__(self, sync_dir: str):
        self.sync_dir = sync_dir
        os.makedirs(sync_dir, exist_ok=True)

    def list_files(self) -> List[str]:
        """列出同步目录中的便签文件"""
        files = []
        if os.path.exists(self.sync_dir):
            for filename in os.listdir(self.sync_dir):
                if filename.startswith('note_') and filename.endswith('.json'):
                    files.append(filename)
        return files

    def copy_to_sync(self, local_path: str, filename: str) -> bool:
        """复制本地文件到同步目录"""
        try:
            dest = os.path.join(self.sync_dir, filename)
            shutil.copy2(local_path, dest)
            return True
        except Exception as e:
            logger.error(f'复制到同步目录失败: {filename} - {e}')
            return False

    def copy_from_sync(self, filename: str, local_path: str) -> bool:
        """从同步目录复制到本地"""
        try:
            src = os.path.join(self.sync_dir, filename)
            shutil.copy2(src, local_path)
            return True
        except Exception as e:
            logger.error(f'从同步目录复制失败: {filename} - {e}')
            return False

    def delete_from_sync(self, filename: str) -> bool:
        """从同步目录删除文件"""
        try:
            path = os.path.join(self.sync_dir, filename)
            if os.path.exists(path):
                os.remove(path)
            return True
        except Exception as e:
            logger.error(f'从同步目录删除失败: {filename} - {e}')
            return False

    def get_file_hash(self, filename: str) -> str:
        """获取同步目录中文件的哈希"""
        path = os.path.join(self.sync_dir, filename)
        if not os.path.exists(path):
            return ''
        try:
            h = hashlib.sha256()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return h.hexdigest()
        except Exception as e:
            logger.error(f'计算哈希失败: {e}')
            return ''

    def get_file_hashes(self) -> Dict[str, str]:
        """获取同步目录中所有文件的哈希"""
        result = {}
        for filename in self.list_files():
            result[filename] = self.get_file_hash(filename)
        return result

# -*- coding: utf-8 -*-
"""
同步元数据管理

跟踪每个文件的本地/远端/基准哈希值，用于三向合并冲突检测。
"""

import os
import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SyncMetadata:
    """同步元数据跟踪器"""

    def __init__(self, metadata_file: str):
        self.metadata_file = metadata_file
        self._data: Dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except Exception as e:
                logger.warning(f'加载同步元数据失败: {e}')
                self._data = {}

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.metadata_file), exist_ok=True)
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f'保存同步元数据失败: {e}')

    def get_file_meta(self, filename: str) -> dict:
        return self._data.get(filename, {
            'local_hash': '',
            'remote_hash': '',
            'base_hash': '',
            'last_sync_time': '',
            'status': 'new',
        })

    def update_file_meta(self, filename: str, **kwargs) -> None:
        if filename not in self._data:
            self._data[filename] = {}
        self._data[filename].update(kwargs)
        self._data[filename]['last_sync_time'] = datetime.now().isoformat()

    def remove_file(self, filename: str) -> None:
        if filename in self._data:
            del self._data[filename]

    @staticmethod
    def compute_hash(file_path: str) -> str:
        """计算文件的 SHA-256 哈希"""
        if not os.path.exists(file_path):
            return ''
        try:
            h = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return h.hexdigest()
        except Exception as e:
            logger.error(f'计算哈希失败: {e}')
            return ''

    def detect_changes(self, notes_dir: str, remote_files: Dict[str, str]) -> Dict[str, str]:
        """
        检测文件变更状态

        Args:
            notes_dir: 本地便签目录
            remote_files: {filename: remote_hash} 远端文件哈希

        Returns:
            {filename: 'upload'|'download'|'conflict'|'delete_local'|'delete_remote'|'none'}
        """
        changes = {}

        # 检查本地文件
        local_files = {}
        for filename in os.listdir(notes_dir):
            if filename.startswith('note_') and filename.endswith('.json'):
                file_path = os.path.join(notes_dir, filename)
                local_files[filename] = self.compute_hash(file_path)

        all_files = set(local_files.keys()) | set(remote_files.keys())

        for filename in all_files:
            meta = self.get_file_meta(filename)
            base_hash = meta.get('base_hash', '')
            local_hash = local_files.get(filename, '')
            remote_hash = remote_files.get(filename, '')

            local_changed = local_hash != base_hash and local_hash != ''
            remote_changed = remote_hash != base_hash and remote_hash != ''

            if local_hash and not remote_hash:
                if base_hash:
                    # 远端删除了，本地也删除
                    changes[filename] = 'delete_local'
                else:
                    # 新本地文件
                    changes[filename] = 'upload'
            elif not local_hash and remote_hash:
                if base_hash:
                    # 本地删除了，远端也删除
                    changes[filename] = 'delete_remote'
                else:
                    # 新远端文件
                    changes[filename] = 'download'
            elif local_changed and not remote_changed:
                changes[filename] = 'upload'
            elif remote_changed and not local_changed:
                changes[filename] = 'download'
            elif local_changed and remote_changed:
                if local_hash == remote_hash:
                    changes[filename] = 'none'
                else:
                    changes[filename] = 'conflict'
            else:
                changes[filename] = 'none'

        return changes

# -*- coding: utf-8 -*-
"""
同步引擎

核心同步逻辑：三向合并（local/remote/base hash），
支持 WebDAV 和本地文件夹两种同步方式。
"""

import os
import logging
from typing import Optional, Dict

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal

from features.sync.metadata import SyncMetadata
from features.sync.conflict import ConflictResolver

logger = logging.getLogger(__name__)


class SyncWorker(QThread):
    """同步工作线程"""

    progress = pyqtSignal(int, int, str)  # (current, total, filename)
    completed = pyqtSignal(dict)  # summary
    error = pyqtSignal(str)

    def __init__(self, engine: 'SyncEngine'):
        super().__init__()
        self.engine = engine
        self._abort = False

    def run(self):
        try:
            summary = self.engine._do_sync()
            if not self._abort:
                self.completed.emit(summary)
        except Exception as e:
            if not self._abort:
                self.error.emit(str(e))

    def abort(self):
        self._abort = True


class SyncEngine(QObject):
    """同步引擎"""

    sync_started = pyqtSignal()
    sync_progress = pyqtSignal(int, int, str)
    sync_completed = pyqtSignal(dict)
    sync_error = pyqtSignal(str)

    def __init__(self, notes_dir: str, config=None):
        super().__init__()
        self.notes_dir = notes_dir
        self.config = config
        self.metadata_file = os.path.join(notes_dir, 'sync_metadata.json')
        self.metadata = SyncMetadata(self.metadata_file)
        self._client = None
        self._worker: Optional[SyncWorker] = None
        self._auto_timer: Optional[QTimer] = None

    def set_client(self, client):
        """设置同步客户端（WebDAVClient 或 LocalSyncClient）"""
        self._client = client

    def sync_now(self) -> None:
        """执行一次同步（异步）"""
        if self._worker and self._worker.isRunning():
            logger.warning('同步正在进行中，忽略重复请求')
            return

        self.sync_started.emit()
        self._worker = SyncWorker(self)
        self._worker.progress.connect(self.sync_progress.emit)
        self._worker.completed.connect(self.sync_completed.emit)
        self._worker.error.connect(self.sync_error.emit)
        self._worker.start()

    def start_auto_sync(self, interval_minutes: int = 5) -> None:
        """启动定时自动同步"""
        self.stop_auto_sync()
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self.sync_now)
        self._auto_timer.start(interval_minutes * 60 * 1000)

    def stop_auto_sync(self) -> None:
        """停止定时自动同步"""
        if self._auto_timer:
            self._auto_timer.stop()
            self._auto_timer = None

    def _do_sync(self) -> dict:
        """执行同步核心逻辑"""
        if not self._client:
            raise RuntimeError('同步客户端未设置')

        summary = {'uploaded': 0, 'downloaded': 0, 'conflicts': 0, 'errors': 0}

        # 获取远端文件哈希
        remote_hashes = self._client.get_file_hashes()

        # 检测变更
        changes = self.metadata.detect_changes(self.notes_dir, remote_hashes)

        total = len(changes)
        current = 0
        strategy = 'newer'
        if self.config:
            strategy = self.config.get('sync.conflict_strategy', 'newer')

        for filename, action in changes.items():
            if self._worker and self._worker._abort:
                break

            current += 1
            self._worker.progress.emit(current, total, filename)

            local_path = os.path.join(self.notes_dir, filename)

            try:
                if action == 'upload':
                    self._client.upload_file(local_path, filename)
                    local_hash = SyncMetadata.compute_hash(local_path)
                    self.metadata.update_file_meta(
                        filename, local_hash=local_hash,
                        remote_hash=local_hash, base_hash=local_hash,
                        status='synced'
                    )
                    summary['uploaded'] += 1

                elif action == 'download':
                    self._client.download_file(filename, local_path)
                    local_hash = SyncMetadata.compute_hash(local_path)
                    self.metadata.update_file_meta(
                        filename, local_hash=local_hash,
                        remote_hash=local_hash, base_hash=local_hash,
                        status='synced'
                    )
                    summary['downloaded'] += 1

                elif action == 'conflict':
                    # 下载远端版本到临时文件
                    temp_path = local_path + '.remote_tmp'
                    self._client.download_file(filename, temp_path)

                    winner = ConflictResolver.resolve(local_path, temp_path, strategy)
                    if winner == temp_path:
                        import shutil
                        shutil.move(temp_path, local_path)
                    else:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)

                    if strategy == 'both':
                        ConflictResolver.create_conflict_copy(temp_path if os.path.exists(temp_path) else local_path, 'remote')

                    local_hash = SyncMetadata.compute_hash(local_path)
                    self.metadata.update_file_meta(
                        filename, local_hash=local_hash,
                        remote_hash=local_hash, base_hash=local_hash,
                        status='synced'
                    )
                    summary['conflicts'] += 1

                elif action == 'delete_local':
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    self.metadata.remove_file(filename)

                elif action == 'delete_remote':
                    self._client.delete_file(filename)
                    self.metadata.remove_file(filename)

            except Exception as e:
                logger.error(f'同步文件失败: {filename} - {e}')
                summary['errors'] += 1

        self.metadata.save()
        return summary

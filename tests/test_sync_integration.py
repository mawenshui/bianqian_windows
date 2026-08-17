# -*- coding: utf-8 -*-
"""Cloud-sync configuration and engine wiring regressions."""

import os
import tempfile
import unittest

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication

from core.manager import StickyNoteManager
from features.secret_storage import protect_secret
from features.sync.local_client import LocalSyncClient
from features.sync.webdav_client import WebDAVClient
from features.sync_dialog import SyncDialog


class _Config:
    def __init__(self, values):
        self.values = dict(values)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value, auto_save=True):
        self.values[key] = value

    def save(self):
        pass


class _SignalEngine(QObject):
    sync_started = pyqtSignal()
    sync_progress = pyqtSignal(int, int, str)
    sync_completed = pyqtSignal(dict)
    sync_error = pyqtSignal(str)

    def sync_now(self):
        self.sync_started.emit()


class _DialogManager:
    def __init__(self, config, engine):
        self.config = config
        self.sync_engine = engine

    def setup_sync_engine(self):
        return self.sync_engine


class TestSyncEngineWiring(unittest.TestCase):
    def _manager(self, notes_dir, values):
        manager = StickyNoteManager.__new__(StickyNoteManager)
        manager.notes_dir = notes_dir
        manager.config = _Config(values)
        manager.sync_engine = None
        return manager

    def test_disabled_sync_keeps_engine_inactive(self):
        with tempfile.TemporaryDirectory() as notes_dir:
            manager = self._manager(notes_dir, {'sync.enabled': False})
            self.assertIsNone(manager.setup_sync_engine())
            self.assertIsNone(manager.sync_engine)

    def test_local_provider_uses_canonical_folder_and_engine_protocol(self):
        with tempfile.TemporaryDirectory() as notes_dir, tempfile.TemporaryDirectory() as remote_dir:
            manager = self._manager(notes_dir, {
                'sync.enabled': True,
                'sync.provider': 'local',
                'sync.local_folder': remote_dir,
                'sync.auto_sync': False,
            })
            engine = manager.setup_sync_engine()
            self.assertIsNotNone(engine)
            self.assertIsInstance(engine._client, LocalSyncClient)
            self.assertEqual(os.path.normcase(engine._client.sync_dir), os.path.normcase(remote_dir))

            local_note = os.path.join(notes_dir, 'note_1.json')
            with open(local_note, 'w', encoding='utf-8') as handle:
                handle.write('{"title":"sync"}')
            self.assertTrue(engine._client.upload_file(local_note, 'note_1.json'))
            self.assertIn('note_1.json', engine._client.get_file_hashes())
            restored = os.path.join(notes_dir, 'note_restored.json')
            self.assertTrue(engine._client.download_file('note_1.json', restored))
            self.assertTrue(os.path.exists(restored))
            self.assertTrue(engine._client.delete_file('note_1.json'))

    def test_legacy_local_folder_is_still_read(self):
        with tempfile.TemporaryDirectory() as notes_dir, tempfile.TemporaryDirectory() as remote_dir:
            manager = self._manager(notes_dir, {
                'sync.enabled': True,
                'sync.provider': 'local',
                'sync.local_folder': '',
                'sync.local.sync_dir': remote_dir,
            })
            engine = manager.setup_sync_engine()
            self.assertIsInstance(engine._client, LocalSyncClient)

    def test_webdav_provider_receives_decrypted_password_without_connecting(self):
        with tempfile.TemporaryDirectory() as notes_dir:
            manager = self._manager(notes_dir, {
                'sync.enabled': True,
                'sync.provider': 'webdav',
                'sync.webdav.url': 'https://dav.example.test/',
                'sync.webdav.username': 'alice',
                'sync.webdav.password_encrypted': protect_secret('not-plaintext'),
                'sync.webdav.remote_path': '/StickyNote/',
            })
            engine = manager.setup_sync_engine()
            self.assertIsInstance(engine._client, WebDAVClient)
            self.assertEqual(engine._client.password, 'not-plaintext')
            self.assertIsNone(engine._client._client)

    def test_webdav_legacy_password_is_read_when_merged_default_is_empty(self):
        with tempfile.TemporaryDirectory() as notes_dir:
            manager = self._manager(notes_dir, {
                'sync.enabled': True,
                'sync.provider': 'webdav',
                'sync.webdav.url': 'https://dav.example.test/',
                'sync.webdav.username': 'legacy-user',
                'sync.webdav.password_encrypted': '',
                'sync.webdav.password': 'legacy-password',
                'sync.webdav.remote_path': '/StickyNote/',
            })
            engine = manager.setup_sync_engine()
            self.assertIsInstance(engine._client, WebDAVClient)
            self.assertEqual(engine._client.password, 'legacy-password')


class TestSyncDialogLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.app = QApplication.instance() or QApplication([])

    def test_legacy_path_fallback_and_engine_feedback_reenable_actions(self):
        with tempfile.TemporaryDirectory() as legacy_dir:
            config = _Config({
                'sync.enabled': True,
                'sync.provider': 'local',
                'sync.local_folder': '',
                'sync.local.sync_dir': legacy_dir,
            })
            engine = _SignalEngine()
            dialog = SyncDialog(_DialogManager(config, engine))
            self.assertEqual(dialog.local_dir_input.text(), legacy_dir)

            dialog._on_sync_now()
            self.assertFalse(dialog.sync_btn.isEnabled())
            self.assertFalse(dialog.progress_bar.isHidden())
            engine.sync_progress.emit(1, 2, 'note_1.json')
            self.assertIn('1/2', dialog.status_label.text())
            engine.sync_completed.emit({
                'uploaded': 1, 'downloaded': 1, 'conflicts': 0, 'errors': 0,
            })
            self.assertTrue(dialog.sync_btn.isEnabled())
            self.assertTrue(dialog.progress_bar.isHidden())
            self.assertIn('同步完成', dialog.status_label.text())

            dialog._on_sync_now()
            engine.sync_error.emit('网络不可用')
            self.assertTrue(dialog.sync_btn.isEnabled())
            self.assertTrue(dialog.progress_bar.isHidden())
            self.assertIn('同步失败', dialog.status_label.text())
            dialog.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)

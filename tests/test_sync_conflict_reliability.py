"""Local sync conflict resolution must preserve both versions offline."""

import hashlib
from types import SimpleNamespace

from features.sync.engine import SyncEngine
from features.sync.metadata import SyncMetadata
from features.sync.webdav_client import WebDAVClient
from features.sync.local_client import LocalSyncClient

import pytest


class _LocalClient:
    def __init__(self, remote):
        self.remote = remote

    def get_file_hashes(self):
        return {'note_1.json': hashlib.sha256(self.remote).hexdigest()}

    def download_file(self, _name, path):
        with open(path, 'wb') as stream:
            stream.write(self.remote)

    def upload_file(self, path, _name):
        with open(path, 'rb') as stream:
            self.remote = stream.read()


def test_both_strategy_preserves_remote_copy_and_converges_primary(tmp_path):
    notes = tmp_path / 'notes'
    notes.mkdir()
    local = notes / 'note_1.json'
    local.write_bytes(b'{"title":"local"}')
    remote = b'{"title":"remote"}'
    client = _LocalClient(remote)
    engine = SyncEngine(str(notes), config=SimpleNamespace(
        get=lambda _key, _default: 'both'))
    engine.set_client(client)
    engine.metadata.detect_changes = lambda _notes, _remote: {'note_1.json': 'conflict'}
    engine._worker = SimpleNamespace(_abort=False,
                                     progress=SimpleNamespace(emit=lambda *_args: None))
    result = engine._do_sync()
    assert result == {'uploaded': 0, 'downloaded': 0, 'conflicts': 1, 'errors': 0}
    assert local.read_bytes() == client.remote == b'{"title":"local"}'
    copies = list((notes / 'conflicts').glob('note_1.conflict_remote_*.json'))
    assert len(copies) == 1 and copies[0].read_bytes() == remote
    assert not (notes / 'note_1.json.remote_tmp').exists()


def test_failed_upload_is_not_reported_as_synced(tmp_path):
    notes = tmp_path / 'notes'
    notes.mkdir()
    (notes / 'note_1.json').write_text('{}', encoding='utf-8')
    engine = SyncEngine(str(notes))
    engine.set_client(SimpleNamespace(get_file_hashes=lambda: {},
                                      upload_file=lambda *_args: False))
    engine.metadata.detect_changes = lambda *_args: {'note_1.json': 'upload'}
    engine._worker = SimpleNamespace(_abort=False,
                                     progress=SimpleNamespace(emit=lambda *_args: None))
    assert engine._do_sync()['errors'] == 1
    assert engine.metadata.get_file_meta('note_1.json')['status'] == 'new'


def test_failed_download_keeps_existing_note_and_cleans_partial_file(tmp_path):
    notes = tmp_path / 'notes'
    notes.mkdir()
    local = notes / 'note_1.json'
    local.write_bytes(b'local original')
    def incomplete_download(_name, path):
        with open(path, 'wb') as stream:
            stream.write(b'partial remote')
        return False
    engine = SyncEngine(str(notes))
    engine.set_client(SimpleNamespace(get_file_hashes=lambda: {'note_1.json': 'remote'},
                                      download_file=incomplete_download))
    engine.metadata.detect_changes = lambda *_args: {'note_1.json': 'download'}
    engine._worker = SimpleNamespace(_abort=False,
                                     progress=SimpleNamespace(emit=lambda *_args: None))
    assert engine._do_sync()['errors'] == 1
    assert local.read_bytes() == b'local original'
    assert not (notes / 'note_1.json.download_tmp').exists()


def test_missing_peer_file_never_silently_deletes_only_copy(tmp_path):
    notes = tmp_path / 'notes'
    notes.mkdir()
    local = notes / 'note_1.json'
    local.write_bytes(b'original')
    meta = SyncMetadata(str(notes / 'sync_metadata.json'))
    digest = hashlib.sha256(b'original').hexdigest()
    meta.update_file_meta('note_1.json', base_hash=digest)
    assert meta.detect_changes(str(notes), {})['note_1.json'] == 'upload'
    local.unlink()
    assert meta.detect_changes(str(notes), {'note_1.json': digest})['note_1.json'] == 'download'


def test_missing_local_sync_folder_is_error_not_remote_deletion(tmp_path):
    remote = tmp_path / 'remote'
    client = LocalSyncClient(str(remote))
    remote.rmdir()
    with pytest.raises(OSError):
        client.get_file_hashes()


def test_webdav_reports_content_hash_and_propagates_listing_failure(tmp_path):
    remote_content = b'{"title":"remote"}'
    class FakeDav:
        def list(self, _path):
            return ['note_1.json']
        def info(self, _path):
            return {'etag': 'etag-1'}
        def download(self, _path, local_path):
            with open(local_path, 'wb') as stream:
                stream.write(remote_content)
    wrapper = WebDAVClient('https://example.invalid', 'user', 'password')
    fake = FakeDav()
    wrapper._ensure_client = lambda: fake
    assert wrapper.get_file_hashes()['note_1.json'] == hashlib.sha256(remote_content).hexdigest()
    def fail_list(_path):
        raise OSError('offline')
    fake.list = fail_list
    with pytest.raises(OSError, match='offline'):
        wrapper.get_file_hashes()


def test_webdav_rejects_download_failure_instead_of_hashing_empty_temp_file():
    class FakeDav:
        def list(self, _path):
            return ['note_1.json']
        def info(self, _path):
            return {}
        def download(self, _path, _target):
            return False
    wrapper = WebDAVClient('https://example.invalid', 'user', 'password')
    wrapper._ensure_client = lambda: FakeDav()
    with pytest.raises(OSError, match='下载失败'):
        wrapper.get_file_hashes()

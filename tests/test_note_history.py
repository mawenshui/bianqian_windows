"""Local revision storage, encryption, and resource recovery."""

import json
import io
import os
import uuid
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import core  # Ensure core.manager has finished importing backup before direct feature import.
from features.note_history import HistoryLockedError, NoteHistoryStore
from features.backup import BackupManager
from features.note_lifecycle import NoteLifecycle


def _note(note_uuid, text, **extra):
    return {'note_uuid': note_uuid, 'title': text, 'plain_content': text,
            'attachments': [], 'background_image': '', **extra}


def test_capture_coalesces_edits_and_skips_geometry(tmp_path):
    notes = tmp_path / 'notes'
    notes.mkdir()
    store = NoteHistoryStore(str(notes))
    identity = uuid.uuid4().hex
    assert store.capture(1, _note(identity, 'one'))
    assert not store.capture(1, _note(identity, 'one', x=42))
    assert not store.capture(1, _note(identity, 'two'))
    assert len(store.list_versions(identity)) == 1
    assert store.capture(1, _note(identity, 'two'), force=True)
    older = store.list_versions(identity)[-1]['snapshot']
    restored, resources = store.restore_data(identity, older)
    assert restored['plain_content'] == 'one'
    assert resources == {}


def test_deleted_attachment_is_embedded_in_snapshot(tmp_path):
    notes = tmp_path / 'notes'
    asset = notes / 'attachments' / 'note_1' / (uuid.uuid4().hex + '_demo.txt')
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b'original attachment')
    store = NoteHistoryStore(str(notes))
    identity = uuid.uuid4().hex
    data = _note(identity, 'attached', attachments=[{'path': asset.relative_to(notes).as_posix()}])
    assert store.capture(1, data)
    snapshot = store.list_versions(identity)[0]['snapshot']
    os.remove(asset)
    restored, resources = store.restore_data(identity, snapshot)
    assert restored['attachments'] == data['attachments']
    assert resources[data['attachments'][0]['path']] == b'original attachment'


def test_password_protects_history_and_can_change_or_disable(tmp_path):
    notes = tmp_path / 'notes'
    notes.mkdir()
    identity = uuid.uuid4().hex
    store = NoteHistoryStore(str(notes))
    store.capture(1, _note(identity, 'sensitive'))
    store.change_password('first password')
    snapshot = store._paths(identity)[0]
    assert open(snapshot, 'rb').read().startswith(b'E')
    fresh = NoteHistoryStore(str(notes))
    with pytest.raises(HistoryLockedError):
        fresh.list_versions(identity)
    with pytest.raises(HistoryLockedError):
        fresh.unlock('wrong')
    fresh.unlock('first password')
    fresh.change_password('second password')
    fresh.finalize_password_change()
    with pytest.raises(HistoryLockedError):
        NoteHistoryStore(str(notes)).unlock('first password')
    newer = NoteHistoryStore(str(notes))
    newer.unlock('second password')
    assert newer.list_versions(identity)[0]['data']['plain_content'] == 'sensitive'
    newer.disable_password()
    assert open(snapshot, 'rb').read().startswith(b'P')
    assert not (tmp_path / 'history' / 'key.json').exists()


def test_corrupt_snapshot_rejected_without_touching_note(tmp_path):
    notes = tmp_path / 'notes'
    notes.mkdir()
    identity = uuid.uuid4().hex
    store = NoteHistoryStore(str(notes))
    store.capture(1, _note(identity, 'original'))
    snapshot = store.list_versions(identity)[0]['snapshot']
    with open(store._paths(identity)[0], 'wb') as stream:
        stream.write(b'corrupt')
    with pytest.raises((ValueError, OSError)):
        store.restore_data(identity, snapshot)


def test_corrupt_latest_snapshot_does_not_hide_older_versions_or_block_new_captures(tmp_path):
    notes = tmp_path / 'notes'
    notes.mkdir()
    identity = uuid.uuid4().hex
    store = NoteHistoryStore(str(notes))
    assert store.capture(1, _note(identity, 'older'))
    assert store.capture(1, _note(identity, 'newer'), force=True)
    latest = store._paths(identity)[-1]
    with open(latest, 'wb') as stream:
        stream.write(b'corrupt')
    versions = store.list_versions(identity)
    assert [row['data']['plain_content'] for row in versions] == ['older']
    assert store.capture(1, _note(identity, 'current'))
    assert [row['data']['plain_content'] for row in store.list_versions(identity)] == [
        'current', 'older']


def test_malformed_but_readable_history_metadata_is_skipped(tmp_path):
    notes = tmp_path / 'notes'
    notes.mkdir()
    identity = uuid.uuid4().hex
    store = NoteHistoryStore(str(notes))
    store.capture(1, _note(identity, 'older'))
    snapshot = store.list_versions(identity)[0]['snapshot']
    path = store._paths(identity)[0]
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, 'w') as archive:
        archive.writestr('note.json', '[]')
    with open(path, 'wb') as stream:
        stream.write(b'P' + memory.getvalue())
    with pytest.raises(ValueError, match='历史记录版本'):
        store.restore_data(identity, snapshot)
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, 'w') as archive:
        archive.writestr('note.json', json.dumps({
            'format': 1, 'note_uuid': identity,
            'created_at': 'not-a-date', 'fingerprint': 'fake',
            'data': _note(identity, 'damaged')}))
    with open(path, 'wb') as stream:
        stream.write(b'P' + memory.getvalue())
    assert store.list_versions(identity) == []
    assert store.capture(1, _note(identity, 'current'))


def test_full_backup_includes_history_and_key_metadata(tmp_path):
    notes = tmp_path / 'notes'
    notes.mkdir()
    identity = uuid.uuid4().hex
    data = _note(identity, 'snapshot')
    (notes / 'note_1.json').write_text(json.dumps(data), encoding='utf-8')
    store = NoteHistoryStore(str(notes))
    store.capture(1, data)
    store.change_password('backup password')
    manager = SimpleNamespace(notes={}, notes_dir=str(notes),
                              settings_file=str(tmp_path / 'settings.json'))
    backups = tmp_path / 'backups'
    backups.mkdir()
    backup = BackupManager.__new__(BackupManager)
    backup.manager = manager
    backup.backup_dir = str(backups)
    with patch('features.backup.get_user_data_dir', return_value=str(tmp_path)), \
         patch('features.backup.get_styles_dir', return_value=str(tmp_path / 'styles')):
        path = backup.create_backup_internal('history_test')
        assert backup.preview_backup(path)['valid']
    import zipfile
    with zipfile.ZipFile(path) as archive:
        assert 'history/key.json' in archive.namelist()
        assert any(name.endswith('.snap') for name in archive.namelist())


def test_history_restores_attachment_after_trash_id_conflict(tmp_path):
    from core.manager import StickyNoteManager
    notes = tmp_path / 'notes'
    trash = tmp_path / 'trash'
    lifecycle = NoteLifecycle(str(notes), str(trash))
    store = NoteHistoryStore(str(notes))
    identity = uuid.uuid4().hex
    asset_name = uuid.uuid4().hex + '_file.txt'
    asset = notes / 'attachments' / 'note_1' / asset_name
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b'old version')
    old = _note(identity, 'old', attachments=[{'path': 'attachments/note_1/' + asset_name}])
    lifecycle._write(lifecycle.note_path(1), old)
    store.capture(1, old)
    snapshot = store.list_versions(identity)[0]['snapshot']
    trash_name = lifecycle.move_to_trash(1)
    lifecycle._write(lifecycle.note_path(1), _note(uuid.uuid4().hex, 'other'))
    restored_id = lifecycle.restore(trash_name)
    assert restored_id == 2
    current = _note(identity, 'new')
    lifecycle._write(lifecycle.note_path(2), current)
    manager = StickyNoteManager.__new__(StickyNoteManager)
    manager.notes = {}
    manager.notes_dir = str(notes)
    manager.lifecycle = lifecycle
    manager.history_store = store
    manager.search_manager = SimpleNamespace(refresh_index=lambda: None)
    manager.update_tray_menu = lambda: None
    manager.open_note = lambda _note_id: None
    manager.restore_note_history(2, snapshot)
    result = lifecycle._read(lifecycle.note_path(2))
    assert result['title'] == 'old'
    assert result['attachments'][0]['path'] == 'attachments/note_2/' + asset_name
    assert (notes / result['attachments'][0]['path']).read_bytes() == b'old version'

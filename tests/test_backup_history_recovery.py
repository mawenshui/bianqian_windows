"""Full backup recovery keeps note data and encrypted history together."""

import json
import os
import uuid
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import core
from features.backup import BackupManager
from features.note_history import HistoryLockedError, NoteHistoryStore


def _fixture(tmp_path):
    notes = tmp_path / 'notes'
    notes.mkdir()
    backups = tmp_path / 'backups'
    backups.mkdir()
    styles = tmp_path / 'styles'
    styles.mkdir()
    settings = tmp_path / 'settings.json'
    settings.write_text('{}', encoding='utf-8')
    identity = uuid.uuid4().hex
    original = {'note_uuid': identity, 'title': '原始便签',
                'plain_content': '原始正文', 'attachments': [], 'background_image': ''}
    note_file = notes / 'note_1.json'
    note_file.write_text(json.dumps(original), encoding='utf-8')
    history = NoteHistoryStore(str(notes))
    history.capture(1, original)
    history.change_password('test password')
    backup = BackupManager.__new__(BackupManager)
    backup.manager = SimpleNamespace(notes={}, notes_dir=str(notes),
                                     settings_file=str(settings))
    backup.backup_dir = str(backups)
    return backup, history, note_file, styles, identity


def test_restore_recovers_encrypted_history_and_note_together(tmp_path):
    backup, history, note_file, styles, identity = _fixture(tmp_path)
    conflict_dir = note_file.parent / 'conflicts'
    conflict_dir.mkdir()
    conflict = conflict_dir / 'note_1.conflict_remote_20261016_100000_123456.json'
    conflict.write_text('{"title":"remote copy"}', encoding='utf-8')
    with patch('features.backup.get_user_data_dir', return_value=str(tmp_path)), \
         patch('features.backup.get_styles_dir', return_value=str(styles)):
        archive = backup.create_backup_internal('encrypted_history')
        note_file.write_text('{"title":"changed"}', encoding='utf-8')
        conflict.unlink()
        assert backup.restore_backup_internal(archive)
    assert json.loads(note_file.read_text(encoding='utf-8'))['title'] == '原始便签'
    assert json.loads(conflict.read_text(encoding='utf-8'))['title'] == 'remote copy'
    fresh = NoteHistoryStore(str(note_file.parent))
    with pytest.raises(HistoryLockedError):
        fresh.list_versions(identity)
    fresh.unlock('test password')
    assert fresh.list_versions(identity)[0]['data']['plain_content'] == '原始正文'
    assert os.path.isfile(backup.last_safety_backup_path)


def test_restore_failure_rolls_back_notes_and_history(tmp_path, monkeypatch):
    backup, history, note_file, styles, identity = _fixture(tmp_path)
    with patch('features.backup.get_user_data_dir', return_value=str(tmp_path)), \
         patch('features.backup.get_styles_dir', return_value=str(styles)):
        archive = backup.create_backup_internal('before_change')
        note_file.write_text('{"title":"keep current"}', encoding='utf-8')
        before_history = history._paths(identity)[0]
        original_replace = os.replace
        def fail_history_commit(source, target):
            if str(target) == str(tmp_path / 'history') and 'stage' in str(source):
                raise OSError('injected restore failure')
            return original_replace(source, target)
        monkeypatch.setattr('features.backup.os.replace', fail_history_commit)
        with pytest.raises(OSError, match='injected restore failure'):
            backup.restore_backup_internal(archive)
    assert json.loads(note_file.read_text(encoding='utf-8'))['title'] == 'keep current'
    assert os.path.isfile(before_history)
    assert os.path.isfile(backup.last_safety_backup_path)


@pytest.mark.parametrize('manifest', ['[]', 'null', '"bad"'])
def test_preview_rejects_malformed_manifest_without_crashing(tmp_path, manifest):
    backup, _, _, _, _ = _fixture(tmp_path)
    archive = tmp_path / 'bad_manifest.zip'
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr('notes/note_1.json', '{}')
        stream.writestr('manifest.json', manifest)
    result = backup.preview_backup(str(archive))
    assert not result['valid']
    assert any('清单格式无效' in error for error in result['errors'])


def test_preview_rejects_windows_alternate_data_stream_path(tmp_path):
    backup, _, _, _, _ = _fixture(tmp_path)
    archive = tmp_path / 'ads.zip'
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr('styles/theme:secret.css', 'bad')
    result = backup.preview_backup(str(archive))
    assert not result['valid']
    assert any('不安全' in error for error in result['errors'])


def test_preview_rejects_unsafe_attachment_name(tmp_path):
    backup, _, _, _, _ = _fixture(tmp_path)
    archive = tmp_path / 'attachment_ads.zip'
    name = f'notes/attachments/note_1/{uuid.uuid4().hex}_file:stream'
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr('notes/note_1.json', '{}')
        stream.writestr(name, 'bad')
    result = backup.preview_backup(str(archive))
    assert not result['valid']
    assert any('不安全' in error for error in result['errors'])

from unittest.mock import MagicMock, patch

from main import _perform_reset


def test_password_reset_removes_note_resources_trash_backups_and_history(tmp_path, qapp):
    for folder, filename in [('notes/attachments', 'secret.bin'),
                             ('trash', 'deleted.json'),
                             ('backups', 'backup.zip'),
                             ('history', 'key.json')]:
        directory = tmp_path / folder
        directory.mkdir(parents=True)
        (directory / filename).write_text('private', encoding='utf-8')
    (tmp_path / 'presentation_state.json').write_text('{}', encoding='utf-8')
    config = MagicMock()
    with patch('core.get_user_data_dir', return_value=str(tmp_path)), \
         patch('PyQt5.QtWidgets.QMessageBox.information'):
        assert _perform_reset(1, config)
    for name in ('notes', 'trash', 'backups', 'history', 'presentation_state.json'):
        assert not (tmp_path / name).exists()
    config.set.assert_any_call('security.require_master_password', False)


def test_reset_clears_cached_history_encryption_key(tmp_path, qapp):
    from features.note_history import get_history_store
    notes = tmp_path / 'notes'
    notes.mkdir()
    store = get_history_store(str(notes))
    store.change_password('old password')
    assert store._key is not None
    with patch('core.get_user_data_dir', return_value=str(tmp_path)), \
         patch('PyQt5.QtWidgets.QMessageBox.information'):
        assert _perform_reset(1, MagicMock())
    fresh = get_history_store(str(notes))
    assert fresh is not store and fresh._key is None

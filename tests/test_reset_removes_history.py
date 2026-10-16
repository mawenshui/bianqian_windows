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

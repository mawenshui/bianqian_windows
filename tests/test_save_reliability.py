"""Saving and backup must not silently accept an outdated disk snapshot."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from core.note import StickyNote
from core.manager import StickyNoteManager
from features.backup import BackupDialog, BackupManager
from features.import_export import ImportExportDialog


def test_synchronous_save_reports_disk_failure(tmp_path, monkeypatch):
    note = SimpleNamespace(
        _save_timer=SimpleNamespace(stop=Mock()),
        save_note=Mock(), _save_worker=None,
        note_file=str(tmp_path / 'note_1.json'),
        note_data={'plain_content': 'unsaved'}, history_store=None,
    )
    def fail_write(*_args):
        raise OSError('disk full')
    monkeypatch.setattr('core.note._atomic_write_note', fail_write)
    assert StickyNote.save_note_sync(note) is False
    assert note.save_note.called


def test_backup_aborts_if_open_note_save_failed(tmp_path):
    note = SimpleNamespace(note_file=str(tmp_path / 'note_1.json'),
                           _save_worker=None, save_note_sync=lambda: False)
    backup = BackupManager.__new__(BackupManager)
    backup.manager = SimpleNamespace(notes={1: note})
    with pytest.raises(OSError, match='备份已停止'):
        backup.flush_open_notes()


def test_backup_flushes_all_open_note_state_even_without_pending_timer(tmp_path):
    path = tmp_path / 'note_1.json'
    path.write_text('{"plain_content":"old"}', encoding='utf-8')
    note = SimpleNamespace(
        note_file=str(path),
        _save_worker=None,
        _save_timer=SimpleNamespace(isActive=lambda: False),
        save_note_sync=Mock(),
    )
    backup = BackupManager.__new__(BackupManager)
    backup.manager = SimpleNamespace(notes={1: note})
    backup.flush_open_notes()
    note.save_note_sync.assert_called_once_with()


def test_backup_dialog_reports_flush_failure_without_starting_worker():
    dialog = SimpleNamespace(
        backup_manager=SimpleNamespace(flush_open_notes=Mock(side_effect=OSError('disk full'))),
        progress_bar=Mock(), create_backup_btn=Mock(),
    )
    with patch('features.backup.QMessageBox.warning') as warning:
        BackupDialog.create_backup(dialog)
    warning.assert_called_once()
    dialog.progress_bar.setVisible.assert_not_called()


def test_transfer_import_reports_flush_failure_without_touching_library(tmp_path):
    archive = tmp_path / 'transfer.zip'
    archive.write_bytes(b'placeholder')
    manager = SimpleNamespace(
        notes_dir=str(tmp_path / 'notes'),
        backup_manager=SimpleNamespace(flush_open_notes=Mock(side_effect=OSError('disk full'))),
    )
    dialog = SimpleNamespace(manager=manager)
    with patch('features.import_export.QFileDialog.getOpenFileName', return_value=(str(archive), '')), \
         patch('features.transfer_package.TransferPackageService') as service_type, \
         patch('features.import_export.QMessageBox.question', return_value=16384), \
         patch('features.import_export.QMessageBox.warning') as warning:
        service_type.return_value.preview_package.return_value = {
            'valid': True, 'destination_empty': True,
            'note_count': 1, 'attachment_count': 0}
        ImportExportDialog.import_transfer_package(dialog)
    warning.assert_called_once()
    service_type.return_value.import_package.assert_not_called()


def test_exit_stays_open_when_any_note_cannot_save():
    note = SimpleNamespace(note_id=7, save_note_sync=Mock(return_value=False),
                           is_deleted=False, close=Mock())
    manager = StickyNoteManager.__new__(StickyNoteManager)
    manager.notes = {7: note}
    manager.shortcut_manager = SimpleNamespace(cleanup=Mock())
    with patch('core.manager.QMessageBox.warning') as warning, \
         patch('core.manager.QCoreApplication.quit') as quit_app:
        manager.exit_application()
    warning.assert_called_once()
    quit_app.assert_not_called()
    manager.shortcut_manager.cleanup.assert_not_called()
    note.close.assert_not_called()
    assert not note.is_deleted

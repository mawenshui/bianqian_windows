# -*- coding: utf-8 -*-
"""v1.9.0 现有功能优化的本地回归。"""

import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtWidgets import QApplication

from core.manager import fit_layout_geometry
from core import get_project_root
from features.backup import BackupManager
from features.checklist import ChecklistWidget
from features.import_export import format_checklist
from features.note_lifecycle import NoteLifecycle
from features.reminder import ReminderManager
from features.search import LocalNoteRecordCache


class OptimizationCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        test_root = os.path.join(get_project_root(), 'artifacts', 'test-results')
        os.makedirs(test_root, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_root)
        self.addCleanup(self.temp.cleanup)
        self.notes = os.path.join(self.temp.name, 'notes')
        self.trash = os.path.join(self.temp.name, 'trash')
        self.backups = os.path.join(self.temp.name, 'backups')
        for path in (self.notes, self.trash, self.backups):
            os.makedirs(path)

    def write_note(self, note_id, data):
        path = os.path.join(self.notes, f'note_{note_id}.json')
        with open(path, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False)
        return path


class TestBackupPreview(OptimizationCase):
    def test_new_overwrite_same_removed_and_failure_snapshot(self):
        self.write_note(1, {'title': '相同'})
        self.write_note(2, {'title': '旧'})
        backup = BackupManager.__new__(BackupManager)
        backup.manager = SimpleNamespace(notes={}, notes_dir=self.notes,
                                         settings_file=os.path.join(self.temp.name, 'settings.json'))
        backup.backup_dir = self.backups
        with patch('features.backup.get_user_data_dir', return_value=self.temp.name), \
             patch('features.backup.get_styles_dir', return_value=self.temp.name):
            archive = backup.create_backup_internal('baseline')
            self.write_note(2, {'title': '新'})
            os.remove(os.path.join(self.notes, 'note_1.json'))
            self.write_note(3, {'title': '额外'})
            preview = backup.preview_backup(archive)
            self.assertTrue(preview['valid'], preview['errors'])
            self.assertEqual((preview['new_count'], preview['overwrite_count'],
                              preview['removed_count']), (1, 1, 1))
            self.assertTrue(backup.restore_backup_internal(archive))
            self.assertTrue(os.path.isfile(backup.last_safety_backup_path))


class TestLifecyclePreview(OptimizationCase):
    def test_purge_impact_and_unrelated_attachments(self):
        service = NoteLifecycle(self.notes, self.trash)
        self.write_note(1, {'title': '删除', 'attachments': []})
        name = service.move_to_trash(1)
        folder = os.path.join(self.trash, 'attachments', name[:-5])
        os.makedirs(folder)
        with open(os.path.join(folder, 'a' * 32 + '_a.txt'), 'wb') as stream:
            stream.write(b'abc')
        path = os.path.join(self.trash, name)
        data = service._read(path)
        data['trash_attachments'] = name[:-5]
        service._write(path, data)
        other = os.path.join(self.trash, 'attachments', 'note_99_' + 'b' * 32)
        os.makedirs(other)
        with open(os.path.join(other, 'b' * 32 + '_b.txt'), 'wb') as stream:
            stream.write(b'keep')
        self.assertEqual(service.preview_purge([name])['attachment_bytes'], 3)
        service.purge(name)
        self.assertTrue(os.path.isdir(other))

    def test_orphans_archived_before_removal_and_referenced_preserved(self):
        service = NoteLifecycle(self.notes, self.trash)
        folder = os.path.join(self.notes, 'attachments', 'note_1')
        os.makedirs(folder)
        referenced = 'a' * 32 + '_used.txt'
        orphan = 'b' * 32 + '_orphan.txt'
        self.write_note(1, {'attachments': [{'path': f'attachments/note_1/{referenced}'}]})
        for name in (referenced, orphan):
            with open(os.path.join(folder, name), 'wb') as stream:
                stream.write(name.encode())
        self.assertEqual(len(service.scan_orphan_attachments()), 1)
        count, archive = service.archive_and_remove_orphans(self.backups)
        self.assertEqual(count, 1)
        self.assertTrue(os.path.isfile(os.path.join(folder, referenced)))
        self.assertFalse(os.path.exists(os.path.join(folder, orphan)))
        with zipfile.ZipFile(archive) as stream:
            self.assertIn(f'notes/attachments/note_1/{orphan}', stream.namelist())

    def test_changed_orphan_is_kept_after_snapshot(self):
        service = NoteLifecycle(self.notes, self.trash)
        folder = os.path.join(self.notes, 'attachments', 'note_1')
        os.makedirs(folder)
        self.write_note(1, {'attachments': []})
        path = os.path.join(folder, 'c' * 32 + '_new.txt')
        with open(path, 'wb') as stream:
            stream.write(b'old')
        original_scan = service.scan_orphan_attachments
        calls = 0

        def scan_with_change():
            nonlocal calls
            calls += 1
            if calls == 2:
                with open(path, 'wb') as stream:
                    stream.write(b'new')
            return original_scan()

        service.scan_orphan_attachments = scan_with_change
        removed, archive = service.archive_and_remove_orphans(self.backups)
        self.assertEqual(removed, 0)
        with open(path, 'rb') as stream:
            self.assertEqual(stream.read(), b'new')
        self.assertTrue(os.path.isfile(archive))

    def test_cleanup_refuses_failed_snapshot(self):
        service = NoteLifecycle(self.notes, self.trash)
        self.write_note(1, {'title': '保留'})
        name = service.move_to_trash(1)
        old = (datetime.now() - timedelta(days=40)).timestamp()
        os.utime(os.path.join(self.trash, name), (old, old))
        with self.assertRaises(RuntimeError):
            service.cleanup(30, safety_backup=lambda: False)
        self.assertTrue(os.path.isfile(os.path.join(self.trash, name)))


class TestSearchCache(OptimizationCase):
    def test_incremental_and_rebuild(self):
        path = self.write_note(1, {'title': '初始'})
        cache = LocalNoteRecordCache()
        self.assertEqual(cache.records(self.notes)[0][1]['title'], '初始')
        with patch('features.search.json.load', side_effect=AssertionError('unexpected read')):
            self.assertEqual(cache.records(self.notes)[0][1]['title'], '初始')
        self.write_note(1, {'title': '更新内容'})
        self.assertEqual(cache.records(self.notes)[0][1]['title'], '更新内容')
        cache._records = None
        self.assertEqual(cache.records(self.notes)[0][1]['title'], '更新内容')
        os.remove(path)
        self.assertEqual(cache.records(self.notes), [])


class TestReminderUndo(OptimizationCase):
    def test_snooze_complete_undo_and_single_occurrence(self):
        past = (datetime.now() - timedelta(days=1)).isoformat()
        note = SimpleNamespace(note_data={'title': '提醒', 'reminder': {
            'enabled': True, 'datetime': past, 'repeat': 'once'}},
            is_deleted=False, note_id=1,
            text_edit=SimpleNamespace(toPlainText=lambda: ''), save_note=Mock())
        tray = SimpleNamespace(showMessage=Mock(), Information=1)
        manager = ReminderManager(SimpleNamespace(notes={1: note}, tray_icon=tray))
        manager.timer.stop()
        manager.check_reminders()
        manager.check_reminders()
        self.assertEqual(tray.showMessage.call_count, 1)
        manager.snooze(1, 10)
        manager.complete(1)
        self.assertTrue(manager.undo_last_action())
        self.assertFalse(note.note_data['reminder']['completed'])
        self.assertTrue(manager.undo_last_action())
        self.assertEqual(note.note_data['reminder']['snoozed_until'], '')


class TestChecklistAndLayout(OptimizationCase):
    def test_undo_redo_copy_paste_and_export(self):
        note = SimpleNamespace(note_data={'checklist': []}, is_deleted=False, save_note=Mock())
        widget = ChecklistWidget(note)
        self.addCleanup(widget.close)
        widget.input.setText('任务')
        widget.add_item()
        widget.list_widget.item(0).setCheckState(Qt.Checked)
        self.assertTrue(widget.undo())
        self.assertFalse(note.note_data['checklist'][0]['done'])
        self.assertTrue(widget.redo())
        self.assertTrue(note.note_data['checklist'][0]['done'])
        widget.list_widget.item(0).setSelected(True)
        widget.copy_selected()
        widget.paste_items()
        self.assertEqual(len(note.note_data['checklist']), 2)
        self.assertEqual(format_checklist(note.note_data['checklist'], True),
                         '- [x] 任务\n- [x] 任务')

    def test_restore_layout_after_screen_change(self):
        screens = [QRect(0, 0, 1920, 1080), QRect(1920, 0, 1280, 720)]
        saved = {'geometry': [2000, 100, 400, 300], 'screen': [1920, 0, 1280, 720]}
        self.assertEqual(fit_layout_geometry(saved, screens), (2000, 100, 400, 300))
        result = fit_layout_geometry(saved, [QRect(0, 0, 1280, 720)])
        self.assertTrue(0 <= result[0] <= 1280 - result[2])
        self.assertTrue(0 <= result[1] <= 720 - result[3])

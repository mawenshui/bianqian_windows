# -*- coding: utf-8 -*-
"""P1 本地智能视图、附件和提醒的回归验证。"""

import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt5.QtCore import QPoint, QMimeData
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication

from core import get_project_root
from features.attachments import add_attachment, attachment_path
from features.backup import BackupManager
from features.note_lifecycle import NoteLifecycle
from features.reminder import ReminderData, ReminderManager
from features.reminder import ReminderCenterDialog
from features.group_view import GroupViewDialog
from features.search import SearchDialog
from core.note import StickyNote


class LocalCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        root = os.path.join(get_project_root(), 'artifacts', 'test-results')
        os.makedirs(root, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.notes = os.path.join(self.root, 'notes')
        self.trash = os.path.join(self.root, 'trash')
        os.makedirs(self.notes)
        os.makedirs(self.trash)

    def write_note(self, note_id, data):
        path = os.path.join(self.notes, f'note_{note_id}.json')
        with open(path, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False)
        return path


class TestSmartViews(LocalCase):
    def test_save_load_casefold_and_delete_does_not_remove_note(self):
        note_path = self.write_note(1, {'title': '项目', 'tags': ['Work'],
                                        'theme': 'soft_yellow.css', 'content': 'abc'})
        settings = {}
        config = SimpleNamespace(get=lambda key, default=None: settings.get(key, default),
                                 set=lambda key, value: settings.__setitem__(key, value))
        manager = SimpleNamespace(notes={}, notes_dir=self.notes, config=config,
                                  update_tray_menu=Mock(),
                                  tag_manager=SimpleNamespace(get_all_tags=lambda: {'Work': '#fff'}))
        dialog = SearchDialog(manager)
        dialog.tag_filter.setCurrentText('Work')
        dialog.search_input.setText('项目')
        with patch('features.search.QInputDialog.getText', return_value=('我的视图', True)):
            dialog.save_view()
        self.assertEqual(len(settings['smart_views']), 1)
        dialog.clear_filters()
        dialog.apply_conditions(settings['smart_views'][0]['conditions'])
        self.assertEqual(len(dialog.search_results), 1)
        dialog.saved_view_combo.setCurrentIndex(1)
        dialog.delete_view()
        self.assertTrue(os.path.isfile(note_path))

    def test_group_view_and_reminder_center_open_offscreen(self):
        settings = {'ui.group_view': 2, 'ui.group_sort': 0}
        config = SimpleNamespace(get=lambda key, default=None: settings.get(key, default),
                                 set=lambda key, value: settings.__setitem__(key, value))
        manager = SimpleNamespace(
            notes={}, notes_dir=self.notes, config=config,
            tag_manager=SimpleNamespace(get_tag_color=lambda tag: '#999'),
            reminder_manager=SimpleNamespace(list_entries=lambda: []),
        )
        group = GroupViewDialog(manager)
        self.assertEqual(group.stack.currentIndex(), 2)
        group.close()
        center = ReminderCenterDialog(manager)
        self.assertEqual(center.listing.count(), 0)
        center.close()


class TestAttachments(LocalCase):
    def test_note_toolbar_and_pasted_image(self):
        with patch('core.note.get_position_manager') as positions:
            positions.return_value.get_smart_position.return_value = QPoint(40, 40)
            note = StickyNote(1, self.notes, manager=None)
            self.assertEqual(note.attachment_btn.parentWidget().objectName(),
                             'formatListGroup')
            self.assertEqual(note.attachment_btn.accessibleName(), '管理本地附件')
            mime = QMimeData()
            mime.setImageData(QImage(4, 4, QImage.Format_ARGB32))
            note.text_edit.insertFromMimeData(mime)
            self.assertEqual(len(note.note_data['attachments']), 1)
            self.assertIn('1 个', note.attachment_btn.toolTip())
            self.assertTrue(os.path.isfile(attachment_path(
                self.notes, note.note_data['attachments'][0]['path']
            )))
            note.is_deleted = True
            note.close()

    def test_add_trash_restore_with_id_conflict(self):
        source = os.path.join(self.root, 'picture.png')
        with open(source, 'wb') as stream:
            stream.write(b'picture')
        entry = add_attachment(self.notes, 1, source)
        self.write_note(1, {'title': '附件便签', 'attachments': [entry]})
        lifecycle = NoteLifecycle(self.notes, self.trash)
        name = lifecycle.move_to_trash(1)
        self.assertFalse(os.path.exists(attachment_path(self.notes, entry['path'])))
        self.write_note(1, {'title': '占位'})
        restored_id = lifecycle.restore(name)
        self.assertEqual(restored_id, 2)
        data = lifecycle._read(lifecycle.note_path(2))
        self.assertTrue(os.path.isfile(attachment_path(self.notes, data['attachments'][0]['path'])))

    def test_managed_background_roundtrip_and_purge(self):
        images = os.path.join(self.notes, 'images')
        os.makedirs(images)
        image = os.path.join(images, 'background_1_test.png')
        with open(image, 'wb') as stream:
            stream.write(b'img')
        lifecycle = NoteLifecycle(self.notes, self.trash)
        self.write_note(1, {'background_image': 'images/background_1_test.png'})
        name = lifecycle.move_to_trash(1)
        self.assertFalse(os.path.exists(image))
        lifecycle.restore(name)
        self.assertTrue(os.path.exists(image))
        name = lifecycle.move_to_trash(1)
        lifecycle.purge(name)
        self.assertFalse(any(os.scandir(os.path.join(self.trash, 'images'))))

    def test_backup_includes_local_files(self):
        source = os.path.join(self.root, 'file.txt')
        with open(source, 'w', encoding='utf-8') as stream:
            stream.write('离线附件')
        entry = add_attachment(self.notes, 1, source)
        images = os.path.join(self.notes, 'images')
        os.makedirs(images)
        image_path = os.path.join(images, 'background_1_test.png')
        with open(image_path, 'wb') as stream:
            stream.write(b'background')
        self.write_note(1, {'title': '含附件', 'attachments': [entry],
                            'background_image': 'images/background_1_test.png'})
        backup_dir = os.path.join(self.root, 'backups')
        os.makedirs(backup_dir)
        styles = os.path.join(self.root, 'styles')
        os.makedirs(styles)
        settings_file = os.path.join(self.root, 'settings.json')
        with open(settings_file, 'w', encoding='utf-8') as stream:
            stream.write('{}')
        backup = BackupManager.__new__(BackupManager)
        backup.manager = SimpleNamespace(notes_dir=self.notes, settings_file=settings_file)
        backup.backup_dir = backup_dir
        with patch('features.backup.get_user_data_dir', return_value=self.root), \
             patch('features.backup.get_styles_dir', return_value=styles):
            before = backup._get_notes_state_hash()
            archive = backup.create_backup_internal('with_attachment')
            self.assertTrue(backup.preview_backup(archive)['valid'])
            with open(attachment_path(self.notes, entry['path']), 'w', encoding='utf-8') as stream:
                stream.write('已修改')
            with open(image_path, 'wb') as stream:
                stream.write(b'changed')
            self.assertNotEqual(before, backup._get_notes_state_hash())
            self.assertTrue(backup.restore_backup_internal(archive))
        with open(attachment_path(self.notes, entry['path']), encoding='utf-8') as stream:
            self.assertEqual(stream.read(), '离线附件')
        with open(image_path, 'rb') as stream:
            self.assertEqual(stream.read(), b'background')

    def test_path_rejects_escape(self):
        with self.assertRaises(ValueError):
            attachment_path(self.notes, '../settings.json')

    def test_backup_rejects_orphan_attachment(self):
        backup = BackupManager.__new__(BackupManager)
        archive = os.path.join(self.root, 'orphan.zip')
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.writestr('notes/attachments/note_1/' + 'a' * 32 + '_file.txt', b'a')
        self.assertFalse(backup.preview_backup(archive)['valid'])


class TestReminders(LocalCase):
    def test_once_does_not_repeat_next_day(self):
        target = datetime(2026, 10, 1, 9)
        reminder = ReminderData({'enabled': True, 'datetime': target.isoformat(),
                                 'repeat': 'once'})
        self.assertTrue(reminder.is_due(datetime(2026, 10, 2, 10)))
        reminder.last_triggered = '2026-10-02'
        self.assertFalse(reminder.is_due(datetime(2026, 10, 3, 10)))

    def test_weekly_and_monthly_occurrences(self):
        weekly = ReminderData({'enabled': True, 'datetime': '2026-10-05T09:00',
                               'repeat': 'weekly'})
        self.assertTrue(weekly.is_due(datetime(2026, 10, 12, 10)))
        weekly.last_triggered = '2026-10-12'
        self.assertFalse(weekly.is_due(datetime(2026, 10, 12, 11)))
        missed_week = ReminderData({'enabled': True, 'datetime': '2026-10-05T09:00',
                                    'repeat': 'weekly'})
        self.assertTrue(missed_week.is_due(datetime(2026, 10, 12, 8)))
        monthly = ReminderData({'enabled': True, 'datetime': '2026-01-31T09:00',
                                'repeat': 'monthly'})
        self.assertTrue(monthly.is_due(datetime(2026, 2, 28, 10)))
        self.assertTrue(monthly.is_due(datetime(2026, 2, 1, 10)))

    def test_snooze_and_complete(self):
        note = SimpleNamespace(note_data={'title': '提醒', 'reminder': {
            'enabled': True, 'datetime': (datetime.now() - timedelta(days=1)).isoformat(),
            'repeat': 'once'}}, save_note=Mock())
        manager = SimpleNamespace(notes={1: note})
        center = ReminderManager(manager)
        center.timer.stop()
        self.assertEqual(center.list_entries()[0][2], '已到期')
        center.snooze(1, 10)
        self.assertEqual(center.list_entries()[0][2], '未触发')
        center.complete(1)
        self.assertEqual(center.list_entries()[0][2], '已完成')
        self.assertFalse(ReminderData(note.note_data['reminder']).is_due())


if __name__ == '__main__':
    unittest.main()

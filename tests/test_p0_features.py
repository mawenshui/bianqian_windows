# -*- coding: utf-8 -*-
"""P0 离线功能的数据安全与关键交互回归。"""

import json
import os
import tempfile
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch, Mock

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from core.manager import StickyNoteManager  # 初始化 core 的既有导出顺序
from core.note import _atomic_write_note
from core import get_project_root
from features.backup import BackupManager
from features.checklist import ChecklistWidget
from features.import_export import preview_txt_import
from features.note_lifecycle import NoteLifecycle
from features.search import SearchDialog, _highlight, _snippet


class P0Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        test_tmp = os.path.join(get_project_root(), 'artifacts', 'test-results')
        os.makedirs(test_tmp, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_tmp)
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.notes_dir = os.path.join(self.root, 'notes')
        self.trash_dir = os.path.join(self.root, 'trash')
        os.makedirs(self.notes_dir)
        os.makedirs(self.trash_dir)

    def write_note(self, note_id, data):
        path = os.path.join(self.notes_dir, f'note_{note_id}.json')
        with open(path, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False)
        return path


class TestLifecycle(P0Case):
    def test_atomic_note_write_preserves_old_file_on_failure(self):
        path = self.write_note(1, {'title': '旧内容'})
        with patch('core.note.os.replace', side_effect=OSError('写入失败')):
            with self.assertRaises(OSError):
                _atomic_write_note(path, {'title': '新内容'})
        with open(path, encoding='utf-8') as stream:
            self.assertEqual(json.load(stream)['title'], '旧内容')
        self.assertFalse(any(name.endswith('.tmp') for name in os.listdir(self.notes_dir)))

    def test_archive_trash_restore_and_id_conflict(self):
        service = NoteLifecycle(self.notes_dir, self.trash_dir)
        self.write_note(1, {'title': '私人便签', 'content': '内容', 'locked': True})
        service.set_archived(1, True)
        self.assertEqual(service.list_archive()[0]['id'], 1)
        service.set_archived(1, False)
        name = service.move_to_trash(1)
        self.assertFalse(os.path.exists(service.note_path(1)))
        self.assertEqual(service.list_trash()[0]['title'], '私人便签')
        self.write_note(1, {'title': '新便签'})
        restored_id = service.restore(name)
        self.assertEqual(restored_id, 2)
        self.assertTrue(os.path.exists(service.note_path(1)))
        self.assertEqual(service._read(service.note_path(2))['title'], '私人便签')
        self.assertNotIn('trashed_at', service._read(service.note_path(2)))

    def test_invalid_trash_name_cannot_escape_directory(self):
        service = NoteLifecycle(self.notes_dir, self.trash_dir)
        with self.assertRaises(ValueError):
            service.restore('../note_1.json')
        with self.assertRaises(ValueError):
            service.purge('other.json')

    def test_manager_archives_and_trashes_without_stale_window_save(self):
        path = self.write_note(3, {'title': '窗口便签'})
        manager = StickyNoteManager.__new__(StickyNoteManager)
        manager.notes_dir = self.notes_dir
        manager.lifecycle = NoteLifecycle(self.notes_dir, self.trash_dir)
        manager.search_manager = SimpleNamespace(refresh_index=Mock())
        manager.update_tray_menu = Mock()
        note = SimpleNamespace(
            note_data={'title': '窗口便签'}, _save_worker=None,
            _save_timer=SimpleNamespace(stop=Mock()), is_deleted=False,
            save_note_sync=Mock(), close=Mock(),
        )
        manager.notes = {3: note}
        manager.archive_note(3)
        self.assertTrue(manager.lifecycle._read(path)['archived'])
        self.assertTrue(note.is_deleted)
        self.assertNotIn(3, manager.notes)
        self.assertEqual(note.close.call_count, 1)
        manager.trash_note(3)
        self.assertFalse(os.path.exists(path))
        self.assertEqual(len(manager.lifecycle.list_trash()), 1)


class TestSearch(P0Case):
    def test_filters_and_highlight_with_local_html(self):
        self.write_note(1, {
            'title': '<私密> 项目', 'content': '<html><body><p>目标内容</p></body></html>',
            'plain_content': '目标内容', 'tags': ['工作'], 'pinned': True,
            'archived': True, 'checklist': [{'text': '一步', 'done': False}],
        })
        self.write_note(2, {'title': '其他', 'content': '目标内容', 'tags': []})
        tag_manager = SimpleNamespace(get_all_tags=lambda: {'工作': '#fff'})
        manager = SimpleNamespace(notes={}, notes_dir=self.notes_dir, tag_manager=tag_manager)
        dialog = SearchDialog(manager)
        self.addCleanup(dialog.close)
        dialog.search_input.setText('目标')
        dialog.tag_filter.setCurrentText('工作')
        dialog.todo_filter.setCurrentIndex(1)
        self.assertEqual(len(dialog.search_results), 1)
        self.assertEqual(dialog.search_results[0][0], 1)
        self.assertIn('&lt;私密&gt;', dialog.results_list.itemWidget(dialog.results_list.item(0)).text())
        self.assertIn('background-color', _highlight('目标内容', '目标'))
        self.assertIn('目标', _snippet('前文' * 100 + '目标内容', '目标'))

    def test_empty_query_uses_status_filter(self):
        self.write_note(1, {'title': '归档', 'content': '', 'archived': True})
        manager = SimpleNamespace(
            notes={}, notes_dir=self.notes_dir,
            tag_manager=SimpleNamespace(get_all_tags=lambda: {})
        )
        dialog = SearchDialog(manager)
        self.addCleanup(dialog.close)
        dialog.state_filter.setCurrentIndex(2)
        self.assertEqual([entry[0] for entry in dialog.search_results], [1])
        dialog.clear_filters()
        self.assertEqual(dialog.results_list.count(), 0)


class TestChecklist(P0Case):
    def test_add_complete_collapse_and_reopen(self):
        note = SimpleNamespace(note_data={'checklist': []}, is_deleted=False, saves=0)
        note.save_note = lambda: setattr(note, 'saves', note.saves + 1)
        widget = ChecklistWidget(note)
        self.addCleanup(widget.close)
        widget.input.setText('买牛奶')
        widget.add_item()
        self.assertEqual(note.note_data['checklist'], [{'text': '买牛奶', 'done': False}])
        widget.list_widget.item(0).setCheckState(Qt.Checked)
        self.assertTrue(note.note_data['checklist'][0]['done'])
        widget.toggle_completed()
        self.assertEqual(widget.list_widget.count(), 0)
        widget.toggle_completed()
        widget.list_widget.item(0).setCheckState(Qt.Unchecked)
        self.assertFalse(note.note_data['checklist'][0]['done'])
        self.assertGreaterEqual(note.saves, 3)


class TestBackup(P0Case):
    def setUp(self):
        super().setUp()
        self.backup_dir = os.path.join(self.root, 'backups')
        self.styles_dir = os.path.join(self.root, 'styles')
        os.makedirs(self.backup_dir)
        os.makedirs(self.styles_dir)
        self.settings_file = os.path.join(self.root, 'settings.json')
        with open(self.settings_file, 'w', encoding='utf-8') as stream:
            json.dump({'theme': 'yellow'}, stream)
        self.manager = SimpleNamespace(
            notes={}, notes_dir=self.notes_dir, settings_file=self.settings_file
        )
        self.backup = BackupManager.__new__(BackupManager)
        self.backup.manager = self.manager
        self.backup.backup_dir = self.backup_dir
        self.data_patch = patch('features.backup.get_user_data_dir', return_value=self.root)
        self.styles_patch = patch('features.backup.get_styles_dir', return_value=self.styles_dir)
        self.data_patch.start()
        self.styles_patch.start()
        self.addCleanup(self.data_patch.stop)
        self.addCleanup(self.styles_patch.stop)

    def test_preview_restore_and_safety_snapshot(self):
        path = self.write_note(1, {'title': '原始', 'content': 'A'})
        backup_path = self.backup.create_backup_internal('good')
        preview = self.backup.preview_backup(backup_path)
        self.assertTrue(preview['valid'])
        self.assertEqual(preview['note_count'], 1)
        self.assertEqual(preview['verification'], 'CRC + SHA256')
        with open(path, 'w', encoding='utf-8') as stream:
            json.dump({'title': '现状', 'content': 'B'}, stream)
        self.assertTrue(self.backup.restore_backup_internal(backup_path))
        with open(path, encoding='utf-8') as stream:
            self.assertEqual(json.load(stream)['title'], '原始')
        self.assertTrue(any(name.startswith('pre_restore_') for name in os.listdir(self.backup_dir)))

    def test_invalid_zip_is_rejected_without_modifying_notes(self):
        path = self.write_note(1, {'title': '保留'})
        malicious = os.path.join(self.backup_dir, 'malicious.zip')
        with zipfile.ZipFile(malicious, 'w') as archive:
            archive.writestr('../outside.json', '{}')
        self.assertFalse(self.backup.preview_backup(malicious)['valid'])
        with self.assertRaises(ValueError):
            self.backup.restore_backup_internal(malicious)
        with open(path, encoding='utf-8') as stream:
            self.assertEqual(json.load(stream)['title'], '保留')

    def test_failed_restore_rolls_back_previous_notes(self):
        path = self.write_note(1, {'title': '备份内容'})
        backup_path = self.backup.create_backup_internal('good')
        self.write_note(1, {'title': '当前内容'})
        original_replace = os.replace
        failures = {'remaining': 1}

        def fail_settings_once(source, target):
            if (target == self.settings_file and 'stage' in source
                    and failures['remaining']):
                failures['remaining'] -= 1
                raise OSError('模拟设置文件写入失败')
            return original_replace(source, target)

        with patch('features.backup.os.replace', side_effect=fail_settings_once):
            with self.assertRaises(OSError):
                self.backup.restore_backup_internal(backup_path)
        with open(path, encoding='utf-8') as stream:
            self.assertEqual(json.load(stream)['title'], '当前内容')


class TestImportPreview(P0Case):
    def test_duplicate_and_partial_read_failure(self):
        valid = os.path.join(self.root, 'one.txt')
        with open(valid, 'w', encoding='utf-8') as stream:
            stream.write('标题\n正文')
        entries, errors = preview_txt_import(
            [valid, os.path.join(self.root, 'missing.txt')],
            [{'title': '标题', 'plain_content': '正文'}],
        )
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]['duplicate'])
        self.assertEqual(len(errors), 1)

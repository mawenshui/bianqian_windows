import json
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest

from features.search import LocalNoteRecordCache, QuickSwitchDialog, matched_note_records
from features.checklist import collect_checklist_items, update_checklist_item
from features.note_lifecycle import NoteLifecycle


def _manager(tmp_path):
    notes = tmp_path / 'notes'
    trash = tmp_path / 'trash'
    lifecycle = NoteLifecycle(str(notes), str(trash))
    cache = LocalNoteRecordCache()
    search = SimpleNamespace(record_cache=cache, refresh_index=lambda: None)
    return SimpleNamespace(notes={}, notes_dir=str(notes), lifecycle=lifecycle,
                           search_manager=search, history_store=None)


def test_quick_switch_uses_same_disk_records_as_search(tmp_path):
    manager = _manager(tmp_path)
    manager.lifecycle._write(manager.lifecycle.note_path(1),
                             {'title': '计划', 'plain_content': '苹果', 'archived': False})
    manager.lifecycle._write(manager.lifecycle.note_path(2),
                             {'title': '旧计划', 'plain_content': '苹果', 'archived': True})
    found = matched_note_records(manager, '苹果')
    assert {row[0] for row in found} == {1, 2}
    assert len(matched_note_records(manager, '', limit=1)) == 1


def test_checklist_legacy_id_migration_and_stale_reference(tmp_path):
    manager = _manager(tmp_path)
    path = manager.lifecycle.note_path(1)
    manager.lifecycle._write(path, {'title': '任务', 'checklist': [
        {'text': '相同', 'done': False}, {'text': '相同', 'done': False}]})
    rows = collect_checklist_items(manager)
    assert [row['item_id'] for row in rows] == ['legacy:0', 'legacy:1']
    assert update_checklist_item(manager, 1, 'legacy:1', '相同', True)
    data = json.loads(open(path, encoding='utf-8').read())
    assert [row['done'] for row in data['checklist']] == [False, True]
    assert len({row['item_id'] for row in data['checklist']}) == 2
    with pytest.raises(LookupError):
        update_checklist_item(manager, 1, 'legacy:0', '已改变', True)
    assert not update_checklist_item(manager, 1, data['checklist'][1]['item_id'], '相同', True)


def test_archived_checklist_is_read_only(tmp_path):
    manager = _manager(tmp_path)
    manager.lifecycle._write(manager.lifecycle.note_path(1), {'title': '归档',
        'archived': True, 'checklist': [{'item_id': 'a' * 32, 'text': '任务', 'done': False}]})
    assert collect_checklist_items(manager) == []
    assert len(collect_checklist_items(manager, True)) == 1
    with pytest.raises(ValueError, match='只读'):
        update_checklist_item(manager, 1, 'a' * 32, '任务', True)


def test_invalid_legacy_index_cannot_update_last_checklist_item(tmp_path):
    manager = _manager(tmp_path)
    path = manager.lifecycle.note_path(1)
    manager.lifecycle._write(path, {'title': '任务', 'checklist': [
        {'text': 'first', 'done': False}, {'text': 'last', 'done': False}]})
    with pytest.raises(LookupError):
        update_checklist_item(manager, 1, 'legacy:-1', 'last', True)
    assert not manager.lifecycle._read(path)['checklist'][-1]['done']


def test_quick_switch_keyboard_selects_and_opens(tmp_path, qapp):
    manager = _manager(tmp_path)
    manager.lifecycle._write(manager.lifecycle.note_path(1),
                             {'title': '苹果一', 'plain_content': '果汁'})
    manager.lifecycle._write(manager.lifecycle.note_path(2),
                             {'title': '苹果二', 'plain_content': '果汁'})
    opened = []
    manager.open_note = opened.append
    dialog = QuickSwitchDialog(manager)
    dialog.show()
    dialog.query.setText('苹果')
    assert dialog.results.count() == 2
    QTest.keyClick(dialog.query, Qt.Key_Down)
    assert dialog.results.currentRow() == 1
    selected = dialog.results.currentItem().data(Qt.UserRole)
    QTest.keyClick(dialog.query, Qt.Key_Return)
    assert opened == [selected]
    dialog.close()

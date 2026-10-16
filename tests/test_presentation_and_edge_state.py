import json
from types import SimpleNamespace

from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication

from core.manager import StickyNoteManager
from core.note import StickyNote
from features.presentation_mode import PresentationState


class _Note:
    def __init__(self, visible=True, edge=False):
        self.visible = visible
        self.auto_hidden = edge
        self._hover_restored = False
        self.hide_tab = None
        self.note_data = {'edge_collapsed': edge}
        self.saved = 0

    def isVisible(self):
        return self.visible

    def save_note_sync(self):
        self.saved += 1

    def hide(self):
        self.visible = False

    def show(self):
        self.visible = True


def _manager(tmp_path, notes):
    manager = StickyNoteManager.__new__(StickyNoteManager)
    manager.notes = notes
    manager.presentation_state = PresentationState(str(tmp_path))
    manager.presentation_active = False
    manager._presentation_snapshot = {}
    manager.app = SimpleNamespace(topLevelWidgets=lambda: [])
    manager.tray_menu = None
    manager._set_presentation_menu_state = lambda: None
    manager.update_tray_menu = lambda: None
    return manager


def test_presentation_state_is_written_before_windows_hide(tmp_path):
    visible = _Note(True)
    hidden = _Note(False)
    manager = _manager(tmp_path, {1: visible, 2: hidden})
    original_hide = visible.hide
    def hide_after_check():
        assert manager.presentation_state.read()['active']
        original_hide()
    visible.hide = hide_after_check
    manager.start_presentation_mode()
    assert manager.presentation_active
    assert not visible.visible and not hidden.visible
    assert manager.presentation_state.read()['notes']['1']['visible']
    assert not manager.presentation_state.read()['notes']['2']['visible']
    manager.end_presentation_mode()
    assert visible.visible and not hidden.visible
    assert not manager.presentation_state.read()['active']


def test_presentation_state_survives_restart(tmp_path):
    state = PresentationState(str(tmp_path))
    state.write(True, {'7': {'visible': True, 'edge': False}})
    second = PresentationState(str(tmp_path))
    assert second.read() == {'active': True,
                             'notes': {'7': {'visible': True, 'edge': False}}}


def test_invalid_presentation_state_rejected(tmp_path):
    path = tmp_path / 'presentation_state.json'
    path.write_text(json.dumps({'active': True, 'notes': []}), encoding='utf-8')
    try:
        PresentationState(str(tmp_path)).read()
    except ValueError:
        pass
    else:
        raise AssertionError('invalid state accepted')


def test_edge_collapse_survives_note_reconstruction(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    app = QApplication.instance() or QApplication([])
    positioning = MagicMock()
    positioning.get_smart_position.return_value = QPoint(200, 200)
    positioning.is_position_valid.return_value = True
    monkeypatch.setattr('core.note.get_position_manager', lambda: positioning)
    notes_dir = tmp_path / 'notes'
    notes_dir.mkdir()
    note = StickyNote(1, str(notes_dir), manager=None)
    note.resize(400, 300)
    note.move(200, 150)
    note._auto_hide_to_edge('left')
    stored = json.loads((notes_dir / 'note_1.json').read_text(encoding='utf-8'))
    assert stored['edge_collapsed'] and stored['hidden_edge'] == 'left'
    assert stored['pre_hide_geometry']['width'] >= 100
    note.is_deleted = True
    note.close()
    rebuilt = StickyNote(1, str(notes_dir), manager=None, preloaded_data=stored)
    assert rebuilt.restore_persisted_edge()
    assert rebuilt.auto_hidden and rebuilt.hide_tab.isVisible()
    assert not rebuilt.isVisible()
    rebuilt.is_deleted = True
    rebuilt.close()

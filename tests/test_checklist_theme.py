"""Checklist controls follow the active note palette without changing item state."""

import uuid
from unittest.mock import patch

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication, QPushButton

from core.note import StickyNote


_app = QApplication.instance() or QApplication([])


@pytest.mark.parametrize('theme', [
    'soft_yellow.css', 'elegant_green.css', 'dark_modern.css',
    'high_contrast.css',
])
def test_checklist_list_input_buttons_and_indicator_use_theme(tmp_path, theme):
    item_id = uuid.uuid4().hex
    data = {
        'title': '清单主题', 'content': '', 'plain_content': '',
        'theme': theme, 'checklist_visible': True,
        'checklist': [{'item_id': item_id, 'text': '已完成', 'done': True}],
    }
    with patch('core.note.get_position_manager') as positions:
        positions.return_value.get_smart_position.return_value = QPoint(100, 100)
        positions.return_value.is_position_valid.return_value = True
        note = StickyNote(1, str(tmp_path), manager=None, preloaded_data=data)
    try:
        checklist = note.checklist_widget
        styles = note._current_theme_styles
        list_css = checklist.list_widget.styleSheet()
        input_css = checklist.input.styleSheet()
        button_css = checklist.findChildren(QPushButton)[0].styleSheet()
        assert f'background-color: {styles["editor_bg"]}' in list_css
        assert checklist.list_widget.viewport().palette().color(QPalette.Base).name() == styles['editor_bg']
        assert f'color: {styles["text"]}' in list_css
        assert f'border: 1px solid {styles["input_border"]}' in list_css
        assert f'background-color: {styles["editor_bg"]}' in input_css
        assert f'background-color: {styles["control_surface"]}' in button_css
        assert 'QListWidget::indicator:checked' in list_css
        assert 'check-light.svg' in list_css or 'check-dark.svg' in list_css
        assert checklist.list_widget.item(0).checkState() == Qt.Checked
        assert checklist._items[0]['item_id'] == item_id
    finally:
        note.is_deleted = True
        note.close()


def test_checklist_rethemes_and_uses_translucent_surface_for_background(tmp_path):
    with patch('core.note.get_position_manager') as positions:
        positions.return_value.get_smart_position.return_value = QPoint(100, 100)
        positions.return_value.is_position_valid.return_value = True
        note = StickyNote(2, str(tmp_path), manager=None)
    try:
        first = note.checklist_widget.list_widget.styleSheet()
        note.set_theme('dark_modern.css')
        dark = note.checklist_widget.list_widget.styleSheet()
        assert dark != first
        assert note._current_theme_styles['editor_bg'] in dark
        note._has_background_image = lambda: True
        note._background_reference_color = lambda: QColor('#808080')
        note.apply_theme()
        assert note._current_theme_styles['editor_alpha'] in note.checklist_widget.list_widget.styleSheet()
        assert note._current_theme_styles['control_alpha'] in (
            note.checklist_widget.findChildren(QPushButton)[0].styleSheet())
    finally:
        note.is_deleted = True
        note.close()

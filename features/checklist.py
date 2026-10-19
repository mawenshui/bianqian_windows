# -*- coding: utf-8 -*-
"""便签内的本地复选框清单。"""

import copy
import json
import os
import re
import uuid

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QApplication, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget, QDialog, QCheckBox, QLabel, QMessageBox,
)


class ChecklistWidget(QWidget):
    def __init__(self, note, parent=None):
        super().__init__(parent)
        self.note = note
        self._items = [
            {'item_id': item.get('item_id') if re.fullmatch(r'[0-9a-f]{32}', str(item.get('item_id', ''))) else uuid.uuid4().hex,
             'text': str(item.get('text', '')), 'done': bool(item.get('done'))}
            for item in note.note_data.get('checklist', [])
            if isinstance(item, dict)
        ]
        self._show_completed = True
        self._undo = []
        self._redo = []
        self.setAccessibleName('便签清单')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)
        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(145)
        self.list_widget.setAccessibleName('清单项目，可勾选或双击修改')
        self.list_widget.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText('新增清单项目')
        self.input.returnPressed.connect(self.add_item)
        row.addWidget(self.input)
        add_button = QPushButton('添加')
        add_button.clicked.connect(self.add_item)
        row.addWidget(add_button)
        remove_button = QPushButton('删除选中')
        remove_button.clicked.connect(self.remove_selected)
        row.addWidget(remove_button)
        undo_button = QPushButton('撤销清单')
        undo_button.clicked.connect(self.undo)
        row.addWidget(undo_button)
        redo_button = QPushButton('重做清单')
        redo_button.clicked.connect(self.redo)
        row.addWidget(redo_button)
        self.toggle_button = QPushButton('折叠已完成')
        self.toggle_button.clicked.connect(self.toggle_completed)
        row.addWidget(self.toggle_button)
        layout.addLayout(row)
        transfer = QHBoxLayout()
        copy_button = QPushButton('复制选中')
        copy_button.clicked.connect(self.copy_selected)
        transfer.addWidget(copy_button)
        paste_button = QPushButton('粘贴项目')
        paste_button.clicked.connect(self.paste_items)
        transfer.addWidget(paste_button)
        layout.addLayout(transfer)
        self.refresh()

    def apply_theme(self, styles, background_active=False, icon_dir=None):
        """Keep the list, editor and actions on the note's current palette."""
        list_bg = styles['editor_alpha'] if background_active else styles['editor_bg']
        button_bg = styles['control_alpha'] if background_active else styles['control_surface']
        button_hover = (styles['control_hover_alpha'] if background_active
                        else styles['control_hover'])
        self.list_widget.setStyleSheet(f'''
            QListWidget {{
                background-color: {list_bg}; color: {styles['text']};
                border: 1px solid {styles['input_border']};
                border-radius: {styles['radius_field']}px;
                padding: 3px;
                selection-background-color: {styles['selection']};
                selection-color: {styles['selection_text']};
            }}
            QListWidget::item {{ padding: 3px 5px; min-height: 20px; }}
            QListWidget::item:hover {{
                background-color: {styles['control_hover']};
                color: {styles['control_text']};
            }}
            QListWidget::item:selected {{
                background-color: {styles['selection']};
                color: {styles['selection_text']};
            }}
            QListWidget:focus {{ border: 2px solid {styles['focus']}; }}
            QListWidget::indicator {{
                width: 15px; height: 15px; border-radius: 3px;
                border: 1px solid {styles['border']};
                background-color: {styles['surface']};
            }}
            QListWidget::indicator:checked {{
                background-color: {styles['accent']};
                border-color: {styles['focus']};
                {self._check_icon_rule(styles, icon_dir)}
            }}
        ''')
        self.input.setStyleSheet(f'''
            QLineEdit {{
                background-color: {list_bg}; color: {styles['text']};
                border: 1px solid {styles['input_border']};
                border-radius: {styles['radius_field']}px;
                padding: 0 8px; min-height: 28px;
                font-size: 9pt; font-weight: normal;
                selection-background-color: {styles['selection']};
                selection-color: {styles['selection_text']};
            }}
            QLineEdit:focus {{ border: 2px solid {styles['focus']}; }}
        ''')
        button_style = f'''
            QPushButton {{
                background-color: {button_bg}; color: {styles['control_text']};
                border: 1px solid {styles['border']}; border-radius: 5px;
                padding: 0 4px; min-height: 28px;
                font-size: 9pt; font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {button_hover}; border-color: {styles['focus']};
            }}
            QPushButton:focus {{ border: 2px solid {styles['focus']}; }}
            QPushButton:disabled {{
                color: {styles['muted']}; background-color: transparent;
                border-color: {styles['border']};
            }}
        '''
        for button in self.findChildren(QPushButton):
            button.setStyleSheet(button_style)

    @staticmethod
    def _check_icon_rule(styles, icon_dir):
        if not icon_dir:
            return ''
        icon = ('check-light.svg' if QColor(styles['accent_text']).lightness() > 128
                else 'check-dark.svg')
        path = os.path.join(icon_dir, icon).replace('\\', '/')
        return f'image: url("{path}");' if os.path.isfile(path) else ''

    def _remember(self):
        self._undo.append(copy.deepcopy(self._items))
        self._undo = self._undo[-50:]
        self._redo.clear()

    def undo(self):
        if not self._undo:
            return False
        self._redo.append(copy.deepcopy(self._items))
        self._items = self._undo.pop()
        self._persist()
        self.refresh()
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append(copy.deepcopy(self._items))
        self._items = self._redo.pop()
        self._persist()
        self.refresh()
        return True

    def copy_selected(self):
        selected = self.list_widget.selectedItems()
        if selected:
            lines = []
            for item in selected:
                entry = self._items[item.data(Qt.UserRole)]
                lines.append(f'- [{"x" if entry["done"] else " "}] {entry["text"]}')
            QApplication.clipboard().setText('\n'.join(lines))

    def paste_items(self):
        """只在显式点击粘贴时读取剪贴板；最多接受 100 行。"""
        pasted = []
        for line in QApplication.clipboard().text().splitlines()[:100]:
            match = re.fullmatch(r'\s*[-*]\s*\[([ xX])\]\s*(.+)', line)
            text = match.group(2).strip() if match else line.strip()
            if text:
                pasted.append({'item_id': uuid.uuid4().hex, 'text': text[:500], 'done': bool(match and match.group(1).lower() == 'x')})
        if pasted:
            self._remember()
            self._items.extend(pasted)
            self._persist()
            self.refresh()

    def _persist(self):
        self.note.note_data['checklist'] = copy.deepcopy(self._items)
        if not self.note.is_deleted:
            self.note.save_note()

    def refresh(self):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        order = sorted(range(len(self._items)), key=lambda index: self._items[index]['done'])
        for index in order:
            data = self._items[index]
            if data['done'] and not self._show_completed:
                continue
            item = QListWidgetItem(data['text'])
            item.setData(Qt.UserRole, index)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
            item.setCheckState(Qt.Checked if data['done'] else Qt.Unchecked)
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)
        done_count = sum(item['done'] for item in self._items)
        self.toggle_button.setText(
            f'{"显示" if not self._show_completed else "折叠"}已完成 ({done_count})'
        )

    def add_item(self):
        text = self.input.text().strip()
        if not text:
            return
        self._remember()
        self._items.append({'item_id': uuid.uuid4().hex, 'text': text, 'done': False})
        self.input.clear()
        self._persist()
        self.refresh()

    def remove_selected(self):
        selected = self.list_widget.selectedItems()
        if not selected:
            return
        index = selected[0].data(Qt.UserRole)
        self._remember()
        del self._items[index]
        self._persist()
        self.refresh()

    def toggle_completed(self):
        self._show_completed = not self._show_completed
        self.refresh()

    def _on_item_changed(self, item):
        index = item.data(Qt.UserRole)
        if not isinstance(index, int) or index >= len(self._items):
            return
        text = item.text().strip()
        if not text:
            text = self._items[index]['text']
        updated = {
            'item_id': self._items[index]['item_id'],
            'text': text, 'done': item.checkState() == Qt.Checked
        }
        if updated == self._items[index]:
            return
        self._remember()
        self._items[index] = updated
        self._persist()
        QTimer.singleShot(0, self.refresh)

    def set_done_by_id(self, item_id, done):
        """Use the same undo path as an in-note click."""
        index = next((i for i, entry in enumerate(self._items)
                      if entry['item_id'] == item_id), None)
        if index is None:
            raise LookupError('清单项目已删除，请刷新')
        if self._items[index]['done'] == bool(done):
            return False
        self._remember()
        self._items[index]['done'] = bool(done)
        self._persist()
        self.refresh()
        return True


def collect_checklist_items(manager, include_archived=False):
    from features.search import local_note_records
    rows = []
    for note_id, data, opened, _modified in local_note_records(manager):
        if data.get('archived') and not include_archived:
            continue
        entries = (manager.notes[note_id].checklist_widget._items
                   if opened and hasattr(manager.notes[note_id], 'checklist_widget')
                   else data.get('checklist', []))
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            identity = entry.get('item_id') or f'legacy:{index}'
            rows.append({'note_id': note_id, 'item_id': identity,
                         'index': index, 'text': str(entry.get('text', '')),
                         'done': bool(entry.get('done')),
                         'title': str(data.get('title', f'便签 {note_id}')),
                         'archived': bool(data.get('archived'))})
    return sorted(rows, key=lambda row: (row['done'], row['title'].casefold(), row['index']))


def update_checklist_item(manager, note_id, item_id, expected_text, done):
    """Reject stale item references instead of checking the wrong row."""
    path = manager.lifecycle.note_path(note_id)
    if note_id in manager.notes:
        widget = manager.notes[note_id].checklist_widget
        entry = next((row for row in widget._items if row['item_id'] == item_id), None)
        if entry is None or entry['text'] != expected_text:
            raise LookupError('清单已变化，请刷新后重试')
        return widget.set_done_by_id(item_id, done)
    with open(path, encoding='utf-8') as stream:
        data = json.load(stream)
    if data.get('archived'):
        raise ValueError('归档便签的清单只读')
    items = data.get('checklist', [])
    if isinstance(item_id, str) and item_id.startswith('legacy:'):
        try:
            suffix = item_id.split(':', 1)[1]
            if not re.fullmatch(r'(?:0|[1-9]\d*)', suffix):
                raise ValueError('invalid legacy index')
            legacy_index = int(suffix)
            entry = items[legacy_index]
            if not isinstance(entry, dict) or entry.get('item_id'):
                entry = None
        except (ValueError, IndexError):
            entry = None
    else:
        entry = next((row for row in items if isinstance(row, dict)
                      and row.get('item_id') == item_id), None)
    if entry is None or entry.get('text') != expected_text:
        raise LookupError('清单已变化，请刷新后重试')
    if bool(entry.get('done')) == bool(done):
        return False
    for row in items:
        if isinstance(row, dict) and not re.fullmatch(r'[0-9a-f]{32}', str(row.get('item_id', ''))):
            row['item_id'] = uuid.uuid4().hex
    entry['done'] = bool(done)
    if not re.fullmatch(r'[0-9a-f]{32}', str(data.get('note_uuid', ''))):
        data['note_uuid'] = uuid.uuid4().hex
    from core.note import _atomic_write_note
    _atomic_write_note(path, data, getattr(manager, 'history_store', None))
    manager.search_manager.record_cache.clear()
    manager.search_manager.refresh_index()
    return True


class ChecklistOverviewDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle('清单总览')
        self.resize(620, 520)
        layout = QVBoxLayout(self)
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText('筛选清单或来源便签')
        layout.addWidget(self.filter)
        self.include_archived = QCheckBox('显示归档清单（只读）', self)
        layout.addWidget(self.include_archived)
        self.list_widget = QListWidget(self)
        self.list_widget.setAccessibleName('跨便签清单')
        layout.addWidget(self.list_widget)
        buttons = QHBoxLayout()
        refresh_button = QPushButton('刷新')
        refresh_button.clicked.connect(self.refresh)
        buttons.addWidget(refresh_button)
        locate_button = QPushButton('定位便签')
        locate_button.clicked.connect(self.locate_note)
        buttons.addWidget(locate_button)
        layout.addLayout(buttons)
        self.filter.textChanged.connect(self.refresh)
        self.include_archived.toggled.connect(self.refresh)
        self.list_widget.itemChanged.connect(self._toggle)
        self.refresh()

    def refresh(self, *_args):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        query = self.filter.text().casefold().strip()
        for row in collect_checklist_items(self.manager, self.include_archived.isChecked()):
            if query and query not in (row['text'] + ' ' + row['title']).casefold():
                continue
            item = QListWidgetItem(f'{row["text"]}  · {row["title"]}')
            item.setData(Qt.UserRole, row)
            flags = item.flags() | Qt.ItemIsUserCheckable
            if row['archived'] or not row['item_id']:
                flags &= ~Qt.ItemIsEnabled
            item.setFlags(flags)
            item.setCheckState(Qt.Checked if row['done'] else Qt.Unchecked)
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)

    def _toggle(self, item):
        row = item.data(Qt.UserRole)
        try:
            update_checklist_item(self.manager, row['note_id'], row['item_id'],
                                  row['text'], item.checkState() == Qt.Checked)
        except (LookupError, ValueError, OSError) as exc:
            QMessageBox.warning(self, '清单已变化', str(exc))
        self.refresh()

    def locate_note(self):
        item = self.list_widget.currentItem()
        if item is not None:
            row = item.data(Qt.UserRole)
            if row['archived']:
                QMessageBox.information(self, '归档便签', '请先在归档与回收站中取消归档。')
            else:
                self.manager.open_note(row['note_id'])

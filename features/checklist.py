# -*- coding: utf-8 -*-
"""便签内的本地复选框清单。"""

import copy
import re

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)


class ChecklistWidget(QWidget):
    def __init__(self, note, parent=None):
        super().__init__(parent)
        self.note = note
        self._items = [
            {'text': str(item.get('text', '')), 'done': bool(item.get('done'))}
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
                pasted.append({'text': text[:500], 'done': bool(match and match.group(1).lower() == 'x')})
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
        self._items.append({'text': text, 'done': False})
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
            'text': text, 'done': item.checkState() == Qt.Checked
        }
        if updated == self._items[index]:
            return
        self._remember()
        self._items[index] = updated
        self._persist()
        QTimer.singleShot(0, self.refresh)

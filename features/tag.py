# -*- coding: utf-8 -*-
"""
标签分组管理模块

提供便签标签功能，支持：
- 标签 CRUD（创建、重命名、删除）
- 标签颜色自定义
- 便签多标签关联
- 托盘菜单按标签分组
- 搜索按标签过滤
- 标签数据持久化（tags.json）
"""

import os
import json

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLineEdit, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QColorDialog,
    QMessageBox, QMenu, QAction, QInputDialog,
    QWidget, QCompleter, QFrame, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QStringListModel
from PyQt5.QtGui import QColor, QFont

# 预设标签颜色
TAG_COLORS = [
    '#e74c3c', '#e67e22', '#f1c40f', '#2ecc71',
    '#3498db', '#9b59b6', '#1abc9c', '#34495e',
    '#e91e63', '#00bcd4', '#ff5722', '#607d8b',
]


class TagManager:
    """
    标签管理器

    管理所有标签的增删改查，标签数据存储到 tags.json。
    """

    def __init__(self, manager):
        self.manager = manager
        self.tags_file = os.path.join(os.path.dirname(manager.settings_file), 'tags.json')
        self.tags: dict = self.load_tags()  # {name: color}

    def load_tags(self) -> dict:
        if os.path.exists(self.tags_file):
            try:
                with open(self.tags_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_tags(self):
        try:
            with open(self.tags_file, 'w', encoding='utf-8') as f:
                json.dump(self.tags, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[TagManager] 保存标签失败: {e}")

    def add_tag(self, name: str, color: str = None) -> bool:
        name = name.strip()
        if not name or name in self.tags:
            return False
        if color is None:
            # 自动分配颜色
            used_colors = set(self.tags.values())
            for c in TAG_COLORS:
                if c not in used_colors:
                    color = c
                    break
            if color is None:
                color = TAG_COLORS[len(self.tags) % len(TAG_COLORS)]
        self.tags[name] = color
        self.save_tags()
        return True

    def remove_tag(self, name: str):
        if name in self.tags:
            del self.tags[name]
            self.save_tags()
            # 从所有便签中移除该标签
            for note in self.manager.notes.values():
                tags = note.note_data.get('tags', [])
                if name in tags:
                    tags.remove(name)
                    note.note_data['tags'] = tags
                    note.save_note()

    def rename_tag(self, old_name: str, new_name: str) -> bool:
        new_name = new_name.strip()
        if not new_name or new_name in self.tags:
            return False
        if old_name in self.tags:
            self.tags[new_name] = self.tags.pop(old_name)
            self.save_tags()
            for note in self.manager.notes.values():
                tags = note.note_data.get('tags', [])
                if old_name in tags:
                    tags[tags.index(old_name)] = new_name
                    note.note_data['tags'] = tags
                    note.save_note()
            return True
        return False

    def set_tag_color(self, name: str, color: str):
        if name in self.tags:
            self.tags[name] = color
            self.save_tags()

    def get_tag_color(self, name: str) -> str:
        return self.tags.get(name, '#888888')

    def get_all_tags(self) -> dict:
        return dict(self.tags)

    def get_notes_by_tag(self, tag_name: str) -> list:
        """获取拥有指定标签的便签 ID 列表"""
        result = []
        for note_id, note in self.manager.notes.items():
            if tag_name in note.note_data.get('tags', []):
                result.append(note_id)
        return result


class TagChipWidget(QFrame):
    """便签上的标签芯片组件"""

    removed = pyqtSignal(str)  # 标签被移除时发射

    def __init__(self, tag_name: str, color: str, parent=None):
        super().__init__(parent)
        self.tag_name = tag_name
        self.color = color
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet(f'''
            QFrame {{
                background-color: {color};
                border-radius: 8px;
                padding: 2px 6px;
            }}
            QFrame:hover {{
                opacity: 0.8;
            }}
        ''')
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        layout = QHBoxLayout()
        layout.setContentsMargins(6, 1, 4, 1)
        layout.setSpacing(4)

        label = QLabel(tag_name)
        label.setStyleSheet('color: white; font-size: 10pt; font-weight: bold; background: transparent;')
        layout.addWidget(label)

        close_btn = QPushButton('×')
        close_btn.setFixedSize(14, 14)
        close_btn.setStyleSheet('''
            QPushButton {
                background: rgba(255,255,255,0.3); color: white;
                border-radius: 7px; font-size: 10pt; font-weight: bold;
                border: none;
            }
            QPushButton:hover { background: rgba(255,255,255,0.6); }
        ''')
        close_btn.clicked.connect(lambda: self.removed.emit(self.tag_name))
        layout.addWidget(close_btn)

        self.setLayout(layout)


class TagEditDialog(QDialog):
    """标签编辑对话框（管理所有标签）"""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.tag_manager = manager.tag_manager if hasattr(manager, 'tag_manager') else None
        self.initUI()
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)

    def initUI(self):
        self.setWindowTitle('\u6807\u7b7e\u7ba1\u7406')
        self.setFixedSize(400, 350)

        layout = QVBoxLayout()

        # 新增标签
        add_layout = QHBoxLayout()
        self.new_tag_input = QLineEdit()
        self.new_tag_input.setPlaceholderText('\u8f93\u5165\u65b0\u6807\u7b7e\u540d\u79f0...')
        self.new_tag_input.returnPressed.connect(self.add_tag)
        add_layout.addWidget(self.new_tag_input)

        add_btn = QPushButton('\u6dfb\u52a0')
        add_btn.setFixedWidth(60)
        add_btn.clicked.connect(self.add_tag)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)

        # 标签列表
        self.tag_list = QListWidget()
        self.refresh_tag_list()
        self.tag_list.itemDoubleClicked.connect(self.edit_tag_color)
        layout.addWidget(self.tag_list)

        # 操作按钮
        btn_layout = QHBoxLayout()
        rename_btn = QPushButton('\u91cd\u547d\u540d')
        rename_btn.clicked.connect(self.rename_selected)
        delete_btn = QPushButton('\u5220\u9664')
        delete_btn.clicked.connect(self.delete_selected)
        color_btn = QPushButton('\u6539\u8272')
        color_btn.clicked.connect(self.edit_tag_color)
        btn_layout.addWidget(rename_btn)
        btn_layout.addWidget(color_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def refresh_tag_list(self):
        self.tag_list.clear()
        for name, color in self.tag_manager.get_all_tags().items():
            item = QListWidgetItem(f'  {name}')
            item.setData(Qt.UserRole, name)
            item.setForeground(QColor(color))
            font = QFont()
            font.setBold(True)
            item.setFont(font)
            self.tag_list.addItem(item)

    def add_tag(self):
        name = self.new_tag_input.text().strip()
        if not name:
            return
        if self.tag_manager.add_tag(name):
            self.new_tag_input.clear()
            self.refresh_tag_list()

    def rename_selected(self):
        item = self.tag_list.currentItem()
        if not item:
            return
        old_name = item.data(Qt.UserRole)
        new_name, ok = QInputDialog.getText(
            self, '\u91cd\u547d\u540d', '\u65b0\u540d\u79f0:', text=old_name
        )
        if ok and new_name.strip():
            self.tag_manager.rename_tag(old_name, new_name.strip())
            self.refresh_tag_list()

    def delete_selected(self):
        item = self.tag_list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, '\u5220\u9664\u6807\u7b7e',
            f'\u786e\u5b9a\u5220\u9664\u6807\u7b7e "{name}"\uff1f\n\u5c06\u4ece\u6240\u6709\u4fbf\u7b7e\u4e2d\u79fb\u9664\u8be5\u6807\u7b7e\u3002',
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.tag_manager.remove_tag(name)
            self.refresh_tag_list()

    def edit_tag_color(self):
        item = self.tag_list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        current = QColor(self.tag_manager.get_tag_color(name))
        color = QColorDialog.getColor(current, self, f'\u9009\u62e9 "{name}" \u7684\u989c\u8272')
        if color.isValid():
            self.tag_manager.set_tag_color(name, color.name())
            self.refresh_tag_list()


class NoteTagSelector(QDialog):
    """便签标签选择器 — 为单个便签选择标签"""

    def __init__(self, note, manager, parent=None):
        super().__init__(parent)
        self.note = note
        self.manager = manager
        self.tag_manager = manager.tag_manager
        self.selected_tags = set(note.note_data.get('tags', []))
        self.initUI()
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)

    def initUI(self):
        self.setWindowTitle(f'\u9009\u62e9\u6807\u7b7e - {self.note.note_data.get("title", "")}')
        self.setFixedSize(300, 350)

        layout = QVBoxLayout()

        # 快速创建标签
        create_layout = QHBoxLayout()
        self.create_input = QLineEdit()
        self.create_input.setPlaceholderText('\u65b0\u5efa\u6807\u7b7e...')
        self.create_input.returnPressed.connect(self.create_and_select)
        create_layout.addWidget(self.create_input)
        create_btn = QPushButton('+')
        create_btn.setFixedWidth(30)
        create_btn.clicked.connect(self.create_and_select)
        create_layout.addWidget(create_btn)
        layout.addLayout(create_layout)

        # 标签复选框列表
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        check_widget = QWidget()
        self.check_layout = QVBoxLayout()
        self.check_layout.setSpacing(4)
        self.check_layout.addStretch()
        self.check_boxes = {}

        for name, color in self.tag_manager.get_all_tags().items():
            self._add_tag_checkbox(name, color)

        check_widget.setLayout(self.check_layout)
        scroll.setWidget(check_widget)
        layout.addWidget(scroll)

        # 已选标签显示
        self.selected_label = QLabel()
        self._update_selected_label()
        layout.addWidget(self.selected_label)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton('\u4fdd\u5b58')
        save_btn.clicked.connect(self.save_tags)
        cancel_btn = QPushButton('\u53d6\u6d88')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _add_tag_checkbox(self, name, color):
        from PyQt5.QtWidgets import QCheckBox
        cb = QCheckBox(f'  {name}')
        cb.setChecked(name in self.selected_tags)
        cb.setStyleSheet(f'color: {color}; font-weight: bold;')
        cb.stateChanged.connect(lambda s, n=name: self._on_tag_toggled(n, s))
        self.check_boxes[name] = cb
        # Insert before stretch
        self.check_layout.insertWidget(self.check_layout.count() - 1, cb)

    def _on_tag_toggled(self, name, state):
        if state == Qt.Checked:
            self.selected_tags.add(name)
        else:
            self.selected_tags.discard(name)
        self._update_selected_label()

    def _update_selected_label(self):
        if self.selected_tags:
            self.selected_label.setText('\u5df2\u9009: ' + ', '.join(sorted(self.selected_tags)))
        else:
            self.selected_label.setText('\u672a\u9009\u62e9\u6807\u7b7e')

    def create_and_select(self):
        name = self.create_input.text().strip()
        if not name:
            return
        if name not in self.tag_manager.get_all_tags():
            self.tag_manager.add_tag(name)
            self._add_tag_checkbox(name, self.tag_manager.get_tag_color(name))
        self.selected_tags.add(name)
        if name in self.check_boxes:
            self.check_boxes[name].setChecked(True)
        self.create_input.clear()
        self._update_selected_label()

    def save_tags(self):
        self.note.note_data['tags'] = sorted(self.selected_tags)
        if not self.note.is_deleted:
            self.note.save_note()
        self.accept()

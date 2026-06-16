# -*- coding: utf-8 -*-
"""
便签分组视图模块

提供三种查看模式：
- 看板视图（Kanban）：按标签分列显示
- 网格视图（Grid）：缩略图网格排列
- 列表视图（List）：按时间排序的紧凑列表
"""

import os
import json
import logging
from functools import partial
from typing import Dict, List, Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QLabel, QScrollArea, QWidget, QFrame,
    QComboBox, QGroupBox, QGridLayout, QListWidget,
    QListWidgetItem, QSizePolicy, QMenu, QAction, QMessageBox, QFileDialog, QInputDialog
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QColor, QIcon

logger = logging.getLogger(__name__)


class NoteCard(QFrame):
    """便签缩略图卡片"""

    clicked = pyqtSignal(int)  # note_id

    def __init__(self, note_id: int, title: str, preview: str,
                 tags: List[str] = None, tag_colors: Dict[str, str] = None,
                 is_open: bool = False, parent=None):
        super().__init__(parent)
        self.note_id = note_id
        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedWidth(220)
        self.setMinimumHeight(140)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            NoteCard {
                background-color: #fefef2;
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 4px;
            }
            NoteCard:hover {
                border: 2px solid #4a86e8;
                background-color: #fffff0;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # 标题
        title_label = QLabel(title or f'便签 {note_id}')
        title_label.setFont(QFont('微软雅黑', 11, QFont.Bold))
        title_label.setWordWrap(True)
        title_label.setMaximumHeight(40)
        layout.addWidget(title_label)

        # 预览内容
        preview_label = QLabel(preview[:120] + '...' if len(preview) > 120 else preview)
        preview_label.setWordWrap(True)
        preview_label.setStyleSheet('color: #666; font-size: 9pt;')
        preview_label.setMaximumHeight(60)
        layout.addWidget(preview_label)

        # 标签芯片
        if tags:
            tags_layout = QHBoxLayout()
            tags_layout.setSpacing(4)
            tag_colors = tag_colors or {}
            for tag_name in tags[:3]:  # 最多显示 3 个标签
                color = tag_colors.get(tag_name, '#999')
                tag_chip = QLabel(tag_name)
                tag_chip.setStyleSheet(
                    f'background-color: {color}; color: white; '
                    f'border-radius: 8px; padding: 2px 8px; font-size: 8pt;'
                )
                tag_chip.setFixedHeight(18)
                tags_layout.addWidget(tag_chip)
            tags_layout.addStretch()
            layout.addLayout(tags_layout)

        # 状态指示
        status_layout = QHBoxLayout()
        if is_open:
            status_label = QLabel('● 已打开')
            status_label.setStyleSheet('color: #27ae60; font-size: 8pt;')
        else:
            status_label = QLabel('○ 未打开')
            status_label.setStyleSheet('color: #999; font-size: 8pt;')
        status_layout.addWidget(status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        self.setLayout(layout)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.note_id)
        super().mousePressEvent(event)


class GroupViewDialog(QDialog):
    """便签分组视图对话框"""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle('便签分组视图')
        self.setMinimumSize(900, 600)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowMaximizeButtonHint)
        self._init_ui()
        # 应用主题适配
        try:
            from features.theme_helper import apply_dialog_theme, get_current_theme_css
            apply_dialog_theme(self, get_current_theme_css(manager))
        except Exception:
            pass
        self._refresh_views()

    def _init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # 顶部工具栏
        toolbar = QHBoxLayout()

        title_label = QLabel('便签分组视图')
        title_label.setFont(QFont('微软雅黑', 14, QFont.Bold))
        toolbar.addWidget(title_label)
        toolbar.addStretch()

        # 视图切换
        view_label = QLabel('视图:')
        toolbar.addWidget(view_label)
        self.view_combo = QComboBox()
        self.view_combo.addItems(['看板视图', '网格视图', '列表视图'])
        self.view_combo.currentIndexChanged.connect(self._switch_view)
        self.view_combo.setFixedWidth(120)
        toolbar.addWidget(self.view_combo)

        # 排序
        sort_label = QLabel('排序:')
        toolbar.addWidget(sort_label)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(['最近修改', '创建时间', '标题', '标签数量'])
        self.sort_combo.currentIndexChanged.connect(self._refresh_views)
        self.sort_combo.setFixedWidth(120)
        toolbar.addWidget(self.sort_combo)

        refresh_btn = QPushButton('刷新')
        refresh_btn.clicked.connect(self._refresh_views)
        toolbar.addWidget(refresh_btn)

        main_layout.addLayout(toolbar)

        # 视图容器
        self.stack = QStackedWidget()

        # 看板视图
        self.kanban_scroll = QScrollArea()
        self.kanban_scroll.setWidgetResizable(True)
        self.kanban_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.kanban_scroll.setFrameShape(QFrame.NoFrame)
        self.kanban_widget = QWidget()
        self.kanban_layout = QHBoxLayout(self.kanban_widget)
        self.kanban_layout.setSpacing(16)
        self.kanban_layout.setContentsMargins(8, 8, 8, 8)
        self.kanban_scroll.setWidget(self.kanban_widget)
        self.stack.addWidget(self.kanban_scroll)

        # 网格视图
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.NoFrame)
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setContentsMargins(8, 8, 8, 8)
        self.grid_scroll.setWidget(self.grid_widget)
        self.stack.addWidget(self.grid_scroll)

        # 列表视图
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)  # 多选
        self.list_widget.itemDoubleClicked.connect(self._on_list_item_clicked)
        self.stack.addWidget(self.list_widget)

        main_layout.addWidget(self.stack)

        # 底部按钮
        btn_layout = QHBoxLayout()
        stats_label = QLabel('')
        self._stats_label = stats_label
        btn_layout.addWidget(stats_label)
        btn_layout.addStretch()
        
        # 批量操作按钮
        batch_delete_btn = QPushButton('批量删除')
        batch_delete_btn.setFixedSize(90, 32)
        batch_delete_btn.clicked.connect(self._batch_delete)
        btn_layout.addWidget(batch_delete_btn)
        
        batch_tag_btn = QPushButton('批量标签')
        batch_tag_btn.setFixedSize(90, 32)
        batch_tag_btn.clicked.connect(self._batch_tag)
        btn_layout.addWidget(batch_tag_btn)
        
        batch_export_btn = QPushButton('批量导出')
        batch_export_btn.setFixedSize(90, 32)
        batch_export_btn.clicked.connect(self._batch_export)
        btn_layout.addWidget(batch_export_btn)
        
        close_btn = QPushButton('关闭')
        close_btn.setFixedSize(80, 32)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        main_layout.addLayout(btn_layout)

        self.setLayout(main_layout)

    def _switch_view(self, index):
        self.stack.setCurrentIndex(index)

    def _get_note_infos(self) -> List[dict]:
        """收集所有便签信息"""
        infos = []
        notes = self.manager.notes if self.manager else {}
        tag_manager = self.manager.tag_manager if self.manager else None
        notes_dir = self.manager.notes_dir if self.manager else ''

        # 遍历所有已知的便签文件
        note_ids = set(notes.keys())
        if notes_dir and os.path.exists(notes_dir):
            for fname in os.listdir(notes_dir):
                if fname.startswith('note_') and fname.endswith('.json'):
                    try:
                        nid = int(fname.split('_')[1].split('.')[0])
                        note_ids.add(nid)
                    except Exception:
                        pass

        for nid in note_ids:
            note = notes.get(nid)
            if note:
                title = note.note_data.get('title', f'便签 {nid}')
                plain = note.note_data.get('plain_content', '') or note.text_edit.toPlainText()
                tags = note.note_data.get('tags', [])
                is_open = True
            else:
                # 未打开的便签，从文件读取
                fpath = os.path.join(notes_dir, f'note_{nid}.json')
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    title = data.get('title', f'便签 {nid}')
                    plain = data.get('plain_content', '')
                    tags = data.get('tags', [])
                    is_open = False
                except Exception:
                    continue

            tag_colors = {}
            if tag_manager:
                for t in tags:
                    tag_colors[t] = tag_manager.get_tag_color(t)

            infos.append({
                'id': nid,
                'title': title,
                'preview': plain,
                'tags': tags,
                'tag_colors': tag_colors,
                'is_open': is_open,
            })

        return infos

    def _refresh_views(self):
        """刷新所有视图"""
        infos = self._get_note_infos()

        # 排序
        sort_idx = self.sort_combo.currentIndex() if hasattr(self, 'sort_combo') else 0
        if sort_idx == 0:
            infos.sort(key=lambda x: x['id'], reverse=True)  # 最近修改（ID 大的更新）
        elif sort_idx == 1:
            infos.sort(key=lambda x: x['id'])  # 创建时间
        elif sort_idx == 2:
            infos.sort(key=lambda x: x['title'])  # 标题
        elif sort_idx == 3:
            infos.sort(key=lambda x: len(x['tags']), reverse=True)  # 标签数量

        self._stats_label.setText(f'共 {len(infos)} 个便签')

        self._build_kanban(infos)
        self._build_grid(infos)
        self._build_list(infos)

    def _clear_layout(self, layout):
        """清空布局"""
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            sub = item.layout()
            if sub:
                self._clear_layout(sub)

    def _build_kanban(self, infos: List[dict]):
        """构建看板视图"""
        self._clear_layout(self.kanban_layout)

        # 按标签分组
        tag_groups: Dict[str, List[dict]] = {'未标签': []}
        for info in infos:
            if not info['tags']:
                tag_groups['未标签'].append(info)
            else:
                for tag in info['tags']:
                    if tag not in tag_groups:
                        tag_groups[tag] = []
                    tag_groups[tag].append(info)

        for tag_name, group_infos in sorted(tag_groups.items()):
            column = QFrame()
            column.setFixedWidth(260)
            column.setStyleSheet(
                'QFrame { background-color: #f5f5f5; border-radius: 8px; padding: 4px; }'
            )
            col_layout = QVBoxLayout(column)
            col_layout.setContentsMargins(8, 8, 8, 8)
            col_layout.setSpacing(8)

            # 列标题
            header = QLabel(f'{tag_name} ({len(group_infos)})')
            header.setFont(QFont('微软雅黑', 11, QFont.Bold))
            color = group_infos[0]['tag_colors'].get(tag_name, '#999') if group_infos else '#999'
            header.setStyleSheet(f'color: {color}; padding: 4px;')
            col_layout.addWidget(header)

            # 卡片
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setStyleSheet('background: transparent;')
            cards_widget = QWidget()
            cards_layout = QVBoxLayout(cards_widget)
            cards_layout.setSpacing(8)
            cards_layout.setContentsMargins(0, 0, 0, 0)

            for info in group_infos:
                card = NoteCard(
                    info['id'], info['title'], info['preview'],
                    info['tags'], info['tag_colors'], info['is_open']
                )
                card.clicked.connect(self._open_note)
                cards_layout.addWidget(card)

            cards_layout.addStretch()
            scroll.setWidget(cards_widget)
            col_layout.addWidget(scroll)

            self.kanban_layout.addWidget(column)

        self.kanban_layout.addStretch()

    def _build_grid(self, infos: List[dict]):
        """构建网格视图"""
        self._clear_layout(self.grid_layout)

        for idx, info in enumerate(infos):
            card = NoteCard(
                info['id'], info['title'], info['preview'],
                info['tags'], info['tag_colors'], info['is_open']
            )
            card.clicked.connect(self._open_note)
            row = idx // 4
            col = idx % 4
            self.grid_layout.addWidget(card, row, col)

    def _build_list(self, infos: List[dict]):
        """构建列表视图"""
        self.list_widget.clear()

        for info in infos:
            tags_str = ', '.join(info['tags']) if info['tags'] else '无'
            status = '●' if info['is_open'] else '○'
            text = f"{status}  {info['title']}    [标签: {tags_str}]"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, info['id'])
            item.setSizeHint(QSize(0, 36))
            if info['is_open']:
                item.setForeground(QColor('#27ae60'))
            self.list_widget.addItem(item)

    def _on_list_item_clicked(self, item):
        """列表项双击打开便签"""
        note_id = item.data(Qt.UserRole)
        if note_id is not None:
            self._open_note(note_id)

    def _open_note(self, note_id: int):
        """打开指定便签"""
        if self.manager:
            self.manager.open_note(note_id)
            self.close()

    def _get_selected_note_ids(self) -> list:
        """获取当前列表中选中的便签ID列表"""
        if self.stack.currentIndex() == 2:  # 列表视图
            items = self.list_widget.selectedItems()
            return [item.data(Qt.UserRole) for item in items if item.data(Qt.UserRole) is not None]
        return []

    def _batch_delete(self):
        """批量删除选中的便签"""
        note_ids = self._get_selected_note_ids()
        if not note_ids:
            QMessageBox.information(self, '提示', '请先在列表视图中选择要删除的便签')
            return
        reply = QMessageBox.question(
            self, '确认删除',
            f'确定要删除选中的 {len(note_ids)} 个便签吗？此操作不可恢复！',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes and self.manager:
            self.manager.batch_delete_notes(note_ids)
            self._refresh_views()

    def _batch_tag(self):
        """批量添加标签"""
        note_ids = self._get_selected_note_ids()
        if not note_ids:
            QMessageBox.information(self, '提示', '请先在列表视图中选择便签')
            return
        tag_name, ok = QInputDialog.getText(self, '批量标签', '输入标签名称:')
        if ok and tag_name.strip() and self.manager:
            self.manager.batch_tag_notes(note_ids, tag_name.strip())
            self._refresh_views()

    def _batch_export(self):
        """批量导出便签"""
        note_ids = self._get_selected_note_ids()
        if not note_ids:
            QMessageBox.information(self, '提示', '请先在列表视图中选择便签')
            return
        export_dir = QFileDialog.getExistingDirectory(self, '选择导出目录')
        if export_dir and self.manager:
            count = self.manager.batch_export_notes(note_ids, export_dir)
            QMessageBox.information(self, '导出完成', f'成功导出 {count} 个便签到:\n{export_dir}')

# -*- coding: utf-8 -*-
"""
便签搜索功能模块

提供便签搜索和过滤功能
"""

import os
import json
import logging
import html
import re
import time
from datetime import datetime

logger = logging.getLogger(__name__)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QMessageBox, QComboBox, QTextBrowser, QInputDialog
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QTextDocument


def _plain_content(data):
    plain = data.get('plain_content')
    if isinstance(plain, str):
        return plain
    content = data.get('content', '') or ''
    if not isinstance(content, str):
        return ''
    if '<html' in content.lower() or '<p' in content.lower():
        document = QTextDocument()
        document.setHtml(content)
        return document.toPlainText()
    return content


def _highlight(text, query):
    if not query:
        return html.escape(text)
    return ''.join(
        f'<b style="background-color:#ffe17a;color:#202020">{html.escape(part)}</b>'
        if part.casefold() == query.casefold() else html.escape(part)
        for part in re.split(f'({re.escape(query)})', text, flags=re.IGNORECASE)
    )


def _snippet(content, query, limit=130):
    content = ' '.join(content.split())
    if len(content) <= limit:
        return content
    match = content.casefold().find(query.casefold()) if query else 0
    start = max(0, match - 35) if match >= 0 else 0
    end = min(len(content), start + limit)
    return ('…' if start else '') + content[start:end] + ('…' if end < len(content) else '')


class SearchDialog(QDialog):
    """
    便签搜索对话框
    
    提供搜索便签标题和内容的功能，支持实时搜索和结果预览
    """
    
    note_selected = pyqtSignal(int)  # 选中便签信号
    
    def __init__(self, manager, parent=None):
        """
        初始化搜索对话框
        
        Args:
            manager: 便签管理器实例
            parent: 父窗口
        """
        super().__init__(parent)
        self.manager = manager
        self.search_results = []
        self.initUI()
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        # 应用主题适配
        try:
            from features.theme_helper import apply_dialog_theme, get_current_theme_css
            apply_dialog_theme(self, get_current_theme_css(manager))
        except Exception as e:
            logger.debug(f'应用搜索对话框主题失败: {e}')
        
    def initUI(self):
        """
        初始化用户界面
        """
        self.setWindowTitle('搜索便签')
        self.resize(760, 620)
        
        layout = QVBoxLayout()
        
        # 搜索标题
        title_label = QLabel('搜索便签')
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 搜索输入框
        search_layout = QHBoxLayout()
        search_label = QLabel('搜索:')
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('输入关键词搜索便签标题或内容...')
        self.search_input.textChanged.connect(self.perform_search)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # 标签过滤
        filter_layout = QHBoxLayout()
        filter_label = QLabel('标签筛选:')
        self.tag_filter = QComboBox()
        self.tag_filter.addItem('全部标签')
        self.tag_filter.currentIndexChanged.connect(self.perform_search)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.tag_filter, 1)
        layout.addLayout(filter_layout)

        # 组合筛选均针对本地元数据，空关键词也可使用。
        filter_row = QHBoxLayout()
        second_filter_row = QHBoxLayout()
        self.date_filter = QComboBox()
        for label, days in [('全部时间', 0), ('最近 7 天', 7), ('最近 30 天', 30)]:
            self.date_filter.addItem(label, days)
        self.date_kind = QComboBox()
        self.date_kind.addItem('按修改时间', 'modified')
        self.date_kind.addItem('按创建时间', 'created')
        self.reminder_filter = QComboBox()
        for label, value in [('提醒不限', None), ('有提醒', True), ('无提醒', False)]:
            self.reminder_filter.addItem(label, value)
        self.image_filter = QComboBox()
        for label, value in [('图片/附件不限', None), ('含图片/附件', True), ('无图片/附件', False)]:
            self.image_filter.addItem(label, value)
        self.pin_filter = QComboBox()
        for label, value in [('置顶不限', None), ('已置顶', True), ('未置顶', False)]:
            self.pin_filter.addItem(label, value)
        self.state_filter = QComboBox()
        for label, value in [('活动与归档', 'all'), ('仅活动', 'active'), ('仅归档', 'archived')]:
            self.state_filter.addItem(label, value)
        self.todo_filter = QComboBox()
        self.todo_filter.addItem('清单不限', None)
        self.todo_filter.addItem('仅有未完成项', True)
        self.theme_filter = QComboBox()
        self.theme_filter.addItem('颜色不限', None)
        try:
            from core import get_styles_dir
            for filename in sorted(os.listdir(get_styles_dir())):
                if filename.endswith('.css'):
                    self.theme_filter.addItem(filename[:-4], filename)
        except OSError:
            pass
        self.content_filter = QComboBox()
        for label, kind in [('类型不限', None), ('清单', 'checklist'),
                            ('图片', 'image'), ('附件', 'attachment'), ('纯文字', 'text')]:
            self.content_filter.addItem(label, kind)
        self.content_filter.currentIndexChanged.connect(self.perform_search)
        for combo in (self.date_kind, self.date_filter, self.reminder_filter, self.image_filter,
                      self.pin_filter, self.state_filter, self.todo_filter, self.theme_filter):
            combo.currentIndexChanged.connect(self.perform_search)
            (filter_row if combo in (
                self.date_kind, self.date_filter, self.state_filter
            ) else second_filter_row).addWidget(combo)
        layout.addLayout(filter_row)
        layout.addLayout(second_filter_row)
        third_filter_row = QHBoxLayout()
        third_filter_row.addWidget(self.content_filter)
        layout.addLayout(third_filter_row)
        view_row = QHBoxLayout()
        self.saved_view_combo = QComboBox()
        self.saved_view_combo.addItem('选择智能视图', None)
        self.saved_view_combo.currentIndexChanged.connect(self._load_selected_view)
        view_row.addWidget(self.saved_view_combo, 1)
        save_view = QPushButton('保存条件')
        save_view.clicked.connect(self.save_view)
        view_row.addWidget(save_view)
        delete_view = QPushButton('删除视图')
        delete_view.clicked.connect(self.delete_view)
        view_row.addWidget(delete_view)
        layout.addLayout(view_row)
        clear_button = QPushButton('清除条件')
        clear_button.clicked.connect(self.clear_filters)
        layout.addWidget(clear_button, alignment=Qt.AlignRight)
        
        # 结果统计标签
        self.result_label = QLabel('输入关键词或选择条件开始搜索')
        self.result_label.setStyleSheet('color: #666; font-size: 12px;')
        layout.addWidget(self.result_label)
        
        # 搜索结果列表
        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self.open_selected_note)
        layout.addWidget(self.results_list)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        self.open_button = QPushButton('打开选中')
        self.open_button.clicked.connect(self.open_selected_note)
        self.open_button.setEnabled(False)
        
        self.close_button = QPushButton('关闭')
        self.close_button.clicked.connect(self.close)
        
        button_layout.addWidget(self.open_button)
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # 连接列表选择事件
        self.results_list.itemSelectionChanged.connect(self.on_selection_changed)
        
        # 设置焦点到搜索框
        self.search_input.setFocus()
        self.refresh_saved_views()

    def current_conditions(self):
        return {
            'query': self.search_input.text().strip(),
            'tag': self.tag_filter.currentText(),
            'date_kind': self.date_kind.currentData(),
            'days': self.date_filter.currentData(),
            'reminder': self.reminder_filter.currentData(),
            'image': self.image_filter.currentData(),
            'pin': self.pin_filter.currentData(),
            'state': self.state_filter.currentData(),
            'todo': self.todo_filter.currentData(),
            'theme': self.theme_filter.currentData(),
            'content_type': self.content_filter.currentData(),
        }

    def apply_conditions(self, conditions):
        controls = (
            (self.tag_filter, conditions.get('tag', '全部标签'), True),
            (self.date_kind, conditions.get('date_kind', 'modified'), False),
            (self.date_filter, conditions.get('days', 0), False),
            (self.reminder_filter, conditions.get('reminder'), False),
            (self.image_filter, conditions.get('image'), False),
            (self.pin_filter, conditions.get('pin'), False),
            (self.state_filter, conditions.get('state', 'all'), False),
            (self.todo_filter, conditions.get('todo'), False),
            (self.theme_filter, conditions.get('theme'), False),
            (self.content_filter, conditions.get('content_type'), False),
        )
        self.refresh_tag_filter()
        for combo, value, by_text in controls:
            index = combo.findText(value) if by_text else combo.findData(value)
            combo.setCurrentIndex(index if index >= 0 else 0)
        self.search_input.setText(str(conditions.get('query', '')))
        self.perform_search()

    def refresh_saved_views(self):
        self.saved_view_combo.blockSignals(True)
        self.saved_view_combo.clear()
        self.saved_view_combo.addItem('选择智能视图', None)
        config = getattr(self.manager, 'config', None)
        views = config.get('smart_views', []) if config else []
        for view in (views if isinstance(views, list) else []):
            if isinstance(view, dict) and isinstance(view.get('name'), str):
                self.saved_view_combo.addItem(view['name'], view.get('conditions', {}))
        self.saved_view_combo.blockSignals(False)

    def _load_selected_view(self, index):
        conditions = self.saved_view_combo.itemData(index)
        if isinstance(conditions, dict):
            self.apply_conditions(conditions)

    def save_view(self):
        current = self.saved_view_combo.currentText() if self.saved_view_combo.currentIndex() else ''
        name, ok = QInputDialog.getText(self, '智能视图', '视图名称:', text=current)
        name = name.strip()
        if not ok or not name:
            return
        stored = self.manager.config.get('smart_views', [])
        views = [view for view in (stored if isinstance(stored, list) else [])
                 if isinstance(view, dict) and isinstance(view.get('name'), str)
                 and view['name'].casefold() != name.casefold()]
        views.append({'name': name, 'conditions': self.current_conditions()})
        self.manager.config.set('smart_views', views)
        self.refresh_saved_views()
        self.saved_view_combo.setCurrentIndex(self.saved_view_combo.findText(name))
        self.manager.update_tray_menu()

    def delete_view(self):
        name = self.saved_view_combo.currentText() if self.saved_view_combo.currentIndex() else ''
        if not name:
            return
        stored = self.manager.config.get('smart_views', [])
        views = [view for view in (stored if isinstance(stored, list) else [])
                 if isinstance(view, dict) and view.get('name') != name]
        self.manager.config.set('smart_views', views)
        self.refresh_saved_views()
        self.manager.update_tray_menu()
    
    def refresh_tag_filter(self):
        """刷新标签过滤下拉框"""
        self.tag_filter.blockSignals(True)
        current = self.tag_filter.currentText()
        self.tag_filter.clear()
        self.tag_filter.addItem('全部标签')
        self.tag_filter.addItem('无标签')
        if self.manager and hasattr(self.manager, 'tag_manager'):
            try:
                all_tags = self.manager.tag_manager.get_all_tags()
                for tag_name in sorted(all_tags.keys()):
                    self.tag_filter.addItem(tag_name)
            except Exception as e:
                logger.debug(f'加载标签列表失败: {e}')
        # 恢复之前的选择
        idx = self.tag_filter.findText(current)
        if idx >= 0:
            self.tag_filter.setCurrentIndex(idx)
        self.tag_filter.blockSignals(False)

    def clear_filters(self):
        self.search_input.clear()
        for combo in (self.tag_filter, self.date_kind, self.date_filter, self.reminder_filter,
                      self.image_filter, self.pin_filter, self.state_filter,
                      self.todo_filter, self.theme_filter, self.content_filter):
            combo.setCurrentIndex(0)
        self.perform_search()
        self.search_input.setFocus()

    def _matches_filters(self, data, modified):
        tag = self.tag_filter.currentText()
        tags = data.get('tags') or []
        if tag == '无标签' and tags:
            return False
        if tag not in ('全部标签', '无标签') and not any(
            isinstance(item, str) and item.casefold() == tag.casefold() for item in tags
        ):
            return False
        days = self.date_filter.currentData()
        if days:
            timestamp = modified
            if self.date_kind.currentData() == 'created':
                try:
                    timestamp = datetime.fromisoformat(data.get('created_at', '')).timestamp()
                except (TypeError, ValueError):
                    timestamp = modified
            if timestamp < time.time() - days * 86400:
                return False
        reminder = data.get('reminder')
        has_reminder = isinstance(reminder, dict) and bool(reminder.get('enabled'))
        wanted = self.reminder_filter.currentData()
        if wanted is not None and wanted != has_reminder:
            return False
        content = data.get('content', '') or ''
        has_image = '<img' in content.lower() or bool(data.get('background_image'))
        has_media = has_image or bool(data.get('attachments'))
        wanted = self.image_filter.currentData()
        if wanted is not None and wanted != has_media:
            return False
        wanted = self.pin_filter.currentData()
        if wanted is not None and wanted != bool(data.get('pinned')):
            return False
        state = self.state_filter.currentData()
        if state == 'archived' and not data.get('archived'):
            return False
        if state == 'active' and data.get('archived'):
            return False
        if self.todo_filter.currentData() is True and not any(
            not item.get('done') for item in data.get('checklist', [])
        ):
            return False
        theme = self.theme_filter.currentData()
        if theme is not None and theme != data.get('theme'):
            return False
        kind = self.content_filter.currentData()
        if kind == 'checklist' and not data.get('checklist'):
            return False
        if kind == 'image' and not has_image:
            return False
        if kind == 'attachment' and not data.get('attachments'):
            return False
        if kind == 'text' and (has_media or data.get('checklist')):
            return False
        return True
    
    def perform_search(self, query=None):
        """
        执行搜索操作
        
        Args:
            query: 搜索查询字符串
        """
        self.results_list.clear()
        self.search_results = []
        
        # 刷新标签过滤列表
        self.refresh_tag_filter()
        
        if query is None:
            query = self.search_input.text()
        
        if not isinstance(query, str):
            query = self.search_input.text()
        query = query.strip()
        has_filter = any(combo.currentIndex() for combo in (
            self.tag_filter, self.date_kind, self.date_filter, self.reminder_filter,
            self.image_filter, self.pin_filter, self.state_filter, self.todo_filter,
            self.theme_filter, self.content_filter
        ))
        if not query and not has_filter:
            self.result_label.setText('输入关键词或选择条件开始搜索')
            self.open_button.setEnabled(False)
            return
        folded = query.casefold()
        seen = set()
        records = []
        for note_id, note in self.manager.notes.items():
            note_file = os.path.join(self.manager.notes_dir, f'note_{note_id}.json')
            modified = os.path.getmtime(note_file) if os.path.isfile(note_file) else time.time()
            records.append((note_id, note.note_data, True, modified))
            seen.add(note_id)
        if os.path.isdir(self.manager.notes_dir):
            for filename in os.listdir(self.manager.notes_dir):
                match = re.fullmatch(r'note_(\d+)\.json', filename)
                if not match:
                    continue
                note_id = int(match.group(1))
                if note_id in seen:
                    continue
                note_file = os.path.join(self.manager.notes_dir, filename)
                try:
                    with open(note_file, encoding='utf-8') as stream:
                        data = json.load(stream)
                    records.append((note_id, data, False, os.path.getmtime(note_file)))
                except (OSError, ValueError, TypeError) as exc:
                    logger.warning('搜索便签文件 %s 时出错: %s', filename, exc)
        for note_id, data, opened, modified in records:
            title = str(data.get('title', ''))
            content = _plain_content(data)
            if folded and folded not in title.casefold() and folded not in content.casefold():
                continue
            if not self._matches_filters(data, modified):
                continue
            score = self._compute_relevance(
                folded, title.casefold(), content.casefold(), data.get('tags', [])
            )
            self.search_results.append((note_id, data, opened, score))
        
        # 按相关度降序排列
        self.search_results.sort(key=lambda x: x[3], reverse=True)
        
        self.update_results_display(query)
    
    def _compute_relevance(self, query, title, content, tags):
        """
        计算搜索结果相关度分数
        
        标题精确匹配 > 标题包含 > 内容精确匹配 > 内容包含
        """
        score = 0
        if query == title:
            score += 10
        elif query in title:
            score += 5
        if query in content:
            score += 2
        import re
        if re.search(r'\b' + re.escape(query) + r'\b', title):
            score += 3
        return score
    
    def update_results_display(self, query=None):
        """
        更新搜索结果显示
        """
        self.results_list.clear()
        
        if not self.search_results:
            self.result_label.setText('未找到匹配的便签，请调整关键词或筛选条件')
            self.open_button.setEnabled(False)
            return
        
        self.result_label.setText(f'找到 {len(self.search_results)} 个匹配的便签')
        
        query = self.search_input.text().strip() if query is None else query
        for note_id, data, is_opened, _score in self.search_results:
            title = str(data.get('title') or f'便签 {note_id}')
            preview = _snippet(_plain_content(data), query)
            status = '已归档' if data.get('archived') else ('已打开' if is_opened else '未打开')
            item = QListWidgetItem()
            item.setData(Qt.UserRole, note_id)
            item.setToolTip(f'{status} · ID {note_id}\n{title}\n{preview}')
            self.results_list.addItem(item)
            label = QLabel(
                f'<b>[{status}] {_highlight(title, query)}</b><br>'
                f'<span>{_highlight(preview, query)}</span>'
            )
            label.setWordWrap(True)
            label.setMargin(5)
            label.setMinimumHeight(54)
            item.setSizeHint(label.sizeHint())
            self.results_list.setItemWidget(item, label)
    
    def on_selection_changed(self):
        """
        处理列表选择变化事件
        """
        self.open_button.setEnabled(len(self.results_list.selectedItems()) > 0)
    
    def open_selected_note(self):
        """
        打开选中的便签
        """
        selected_items = self.results_list.selectedItems()
        if not selected_items:
            return
        
        item = selected_items[0]
        note_id = item.data(Qt.UserRole)
        
        try:
            data = next((entry[1] for entry in self.search_results if entry[0] == note_id), {})
            if data.get('archived'):
                preview = QDialog(self)
                preview.setWindowTitle(f'归档预览 · {data.get("title", "便签")}')
                preview.resize(520, 380)
                layout = QVBoxLayout(preview)
                browser = QTextBrowser()
                browser.setPlainText(_plain_content(data))
                layout.addWidget(browser)
                row = QHBoxLayout()
                unarchive_button = QPushButton('取消归档并打开')
                close_button = QPushButton('关闭')
                row.addWidget(unarchive_button)
                row.addWidget(close_button)
                layout.addLayout(row)
                unarchive_button.clicked.connect(preview.accept)
                close_button.clicked.connect(preview.reject)
                if preview.exec_() != QDialog.Accepted:
                    return
                self.manager.unarchive_note(note_id)
            # 如果便签已经打开，直接显示
            if note_id in self.manager.notes:
                note = self.manager.notes[note_id]
                note.show()
                note.raise_()
                note.activateWindow()
            else:
                # 如果便签未打开，先加载然后显示
                self.manager.open_note(note_id)
            
            # 发射信号
            self.note_selected.emit(note_id)
            
            # 关闭搜索对话框
            self.close()
            
        except Exception as e:
            QMessageBox.warning(self, '错误', f'打开便签时出错: {e}')
    
    def keyPressEvent(self, event):
        """
        处理键盘事件
        
        Args:
            event: 键盘事件
        """
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if self.results_list.selectedItems():
                self.open_selected_note()
            elif self.search_results:
                # 如果没有选中项但有搜索结果，选中第一项并打开
                self.results_list.setCurrentRow(0)
                self.open_selected_note()
        else:
            super().keyPressEvent(event)


class SearchManager:
    """
    搜索管理器
    
    管理搜索功能的核心逻辑
    """
    
    def __init__(self, manager):
        """
        初始化搜索管理器
        
        Args:
            manager: 便签管理器实例
        """
        self.manager = manager
        self.search_dialog = None
        self._note_index: dict = {}  # {note_id: {'title': str, 'content': str, 'tags': list}}
        self._index_built = False
        self._build_or_refresh_index()

    def _build_or_refresh_index(self):
        """构建或刷新搜索索引，缓存所有便签的标题和内容"""
        self._note_index.clear()
        notes_dir = self.manager.notes_dir
        if not os.path.exists(notes_dir):
            self._index_built = True
            return
        for filename in os.listdir(notes_dir):
            if filename.startswith('note_') and filename.endswith('.json'):
                try:
                    note_id_str = filename.split('_')[1].split('.')[0]
                    note_id = int(note_id_str)
                    note_file = os.path.join(notes_dir, filename)
                    with open(note_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self._note_index[note_id] = {
                        'title': data.get('title', '').lower(),
                        'content': _plain_content(data).lower(),
                        'tags': data.get('tags', []),
                        'archived': bool(data.get('archived')),
                    }
                except Exception as e:
                    logger.debug(f'索引便签 {filename} 时出错: {e}')
        self._index_built = True

    def refresh_index(self):
        """刷新搜索索引（便签变更后调用）"""
        self._build_or_refresh_index()
    
    def show_search_dialog(self):
        """
        显示搜索对话框
        """
        if self.search_dialog is None or not self.search_dialog.isVisible():
            self.search_dialog = SearchDialog(self.manager)
            self.search_dialog.show()
        else:
            self.search_dialog.raise_()
            self.search_dialog.activateWindow()
    
    def search_notes(self, query):
        """
        搜索便签（程序化接口，使用索引加速）
        
        Args:
            query: 搜索查询字符串
            
        Returns:
            list: 匹配的便签列表 [(note_id, note_data, is_opened), ...]
        """
        results = []
        query_lower = query.lower().strip()
        
        if not query_lower:
            return results

        # 确保索引已构建
        if not self._index_built:
            self._build_or_refresh_index()

        # 搜索已打开的便签
        for note_id, note in self.manager.notes.items():
            title = note.note_data.get('title', '').lower()
            content = _plain_content(note.note_data).lower()
            
            if query_lower in title or query_lower in content:
                results.append((note_id, note.note_data, True))
        
        # 使用索引搜索未打开的便签
        for note_id, index_entry in self._note_index.items():
            if note_id in self.manager.notes:
                continue  # 跳过已打开的
            if query_lower in index_entry['title'] or query_lower in index_entry['content']:
                results.append((note_id, index_entry, False))
        
        return results

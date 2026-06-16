# -*- coding: utf-8 -*-
"""
便签搜索功能模块

提供便签搜索和过滤功能
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, 
    QListWidgetItem, QPushButton, QLabel, QMessageBox, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont


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
        self.setFixedSize(500, 400)
        
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
        
        # 结果统计标签
        self.result_label = QLabel('请输入关键词开始搜索')
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
    
    def refresh_tag_filter(self):
        """刷新标签过滤下拉框"""
        self.tag_filter.blockSignals(True)
        current = self.tag_filter.currentText()
        self.tag_filter.clear()
        self.tag_filter.addItem('全部标签')
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
        
        if len(query.strip()) < 1:
            self.result_label.setText('请输入关键词开始搜索')
            self.open_button.setEnabled(False)
            return
        
        query_lower = query.lower().strip()
        selected_tag = self.tag_filter.currentText()
        
        # 搜索已打开的便签（带相关度评分）
        for note_id, note in self.manager.notes.items():
            title = note.note_data.get('title', '').lower()
            content = note.note_data.get('content', '').lower()
            tags = note.note_data.get('tags', [])
            
            if query_lower in title or query_lower in content:
                # 标签过滤
                if selected_tag != '全部标签' and selected_tag not in tags:
                    continue
                score = self._compute_relevance(query_lower, title, content, tags)
                self.search_results.append((note_id, note, True, score))  # True表示已打开
        
        # 搜索未打开的便签文件（使用 LRU 缓存加速）
        from features.performance import get_note_cache
        cache = get_note_cache()
        notes_dir = self.manager.notes_dir
        if os.path.exists(notes_dir):
            for filename in os.listdir(notes_dir):
                if filename.startswith('note_') and filename.endswith('.json'):
                    try:
                        note_id_str = filename.split('_')[1].split('.')[0]
                        note_id = int(note_id_str)
                        
                        # 跳过已打开的便签
                        if note_id in self.manager.notes:
                            continue
                        
                        # 先查缓存
                        note_data = cache.get(note_id)
                        if note_data is None:
                            # 未命中，从磁盘读取并缓存
                            note_file = os.path.join(notes_dir, filename)
                            with open(note_file, 'r', encoding='utf-8') as f:
                                note_data = json.load(f)
                            cache.put(note_id, note_data)
                        
                        title = note_data.get('title', '').lower()
                        content = note_data.get('content', '').lower()
                        tags = note_data.get('tags', [])
                        
                        if query_lower in title or query_lower in content:
                            # 标签过滤
                            if selected_tag != '全部标签' and selected_tag not in tags:
                                continue
                            score = self._compute_relevance(query_lower, title, content, tags)
                            self.search_results.append((note_id, note_data, False, score))  # False表示未打开
                    
                    except Exception as e:
                        logger.warning(f"搜索便签文件 {filename} 时出错: {e}")
        
        # 按相关度降序排列
        self.search_results.sort(key=lambda x: x[3], reverse=True)
        
        self.update_results_display()
    
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
    
    def update_results_display(self):
        """
        更新搜索结果显示
        """
        self.results_list.clear()
        
        if not self.search_results:
            self.result_label.setText('未找到匹配的便签')
            self.open_button.setEnabled(False)
            return
        
        self.result_label.setText(f'找到 {len(self.search_results)} 个匹配的便签')
        
        for note_id, note_data_or_note, is_opened, score in self.search_results:
            if is_opened:
                # 已打开的便签
                note = note_data_or_note
                title = note.note_data.get('title', f'便签 {note_id}')
                content = note.note_data.get('content', '')
                status = '[已打开]'
            else:
                # 未打开的便签
                note_data = note_data_or_note
                title = note_data.get('title', f'便签 {note_id}')
                content = note_data.get('content', '')
                status = '[未打开]'
            
            # 截取内容预览
            content_preview = content.replace('\n', ' ').strip()
            if len(content_preview) > 100:
                content_preview = content_preview[:100] + '...'
            
            # 创建列表项
            item_text = f"{status} {title}"
            if content_preview:
                item_text += f"\n    {content_preview}"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, note_id)  # 存储便签ID
            
            # 设置不同状态的样式
            if is_opened:
                item.setToolTip(f'便签ID: {note_id}\n状态: 已打开\n标题: {title}\n内容预览: {content_preview}')
            else:
                item.setToolTip(f'便签ID: {note_id}\n状态: 未打开\n标题: {title}\n内容预览: {content_preview}')
            
            self.results_list.addItem(item)
    
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
                        'content': data.get('content', '').lower(),
                        'tags': data.get('tags', []),
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
            content = note.note_data.get('content', '').lower()
            
            if query_lower in title or query_lower in content:
                results.append((note_id, note.note_data, True))
        
        # 使用索引搜索未打开的便签
        for note_id, index_entry in self._note_index.items():
            if note_id in self.manager.notes:
                continue  # 跳过已打开的
            if query_lower in index_entry['title'] or query_lower in index_entry['content']:
                results.append((note_id, index_entry, False))
        
        return results
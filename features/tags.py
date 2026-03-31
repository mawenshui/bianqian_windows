import os
import json
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem, QMessageBox
from PyQt5.QtCore import Qt

class TagManager:
    """
    标签管理器
    """
    def __init__(self, manager):
        self.manager = manager
        self.tags = set()
        self.note_tags = {}  # note_id -> set of tags
        self.tags_file = os.path.join(os.getcwd(), 'tags.json')
        self.load_tags()
    
    def add_tag_to_note(self, note_id, tag):
        """
        为便签添加标签
        
        Args:
            note_id: 便签ID
            tag: 标签名称
        """
        if note_id not in self.note_tags:
            self.note_tags[note_id] = set()
        
        self.note_tags[note_id].add(tag)
        self.tags.add(tag)
        self.save_tags()
    
    def remove_tag_from_note(self, note_id, tag):
        """
        从便签移除标签
        
        Args:
            note_id: 便签ID
            tag: 标签名称
        """
        if note_id in self.note_tags:
            self.note_tags[note_id].discard(tag)
            if not self.note_tags[note_id]:
                del self.note_tags[note_id]
        
        # 检查是否还有其他便签使用此标签
        if not any(tag in tags for tags in self.note_tags.values()):
            self.tags.discard(tag)
        
        self.save_tags()
    
    def get_notes_by_tag(self, tag):
        """
        获取具有指定标签的所有便签
        
        Args:
            tag: 标签名称
            
        Returns:
            便签ID列表
        """
        return [note_id for note_id, tags in self.note_tags.items() if tag in tags]
    
    def get_tags_for_note(self, note_id):
        """
        获取便签的所有标签
        
        Args:
            note_id: 便签ID
            
        Returns:
            标签集合
        """
        return self.note_tags.get(note_id, set())
    
    def get_all_tags(self):
        """
        获取所有标签
        
        Returns:
            标签集合
        """
        return self.tags
    
    def load_tags(self):
        """
        从文件加载标签
        """
        if os.path.exists(self.tags_file):
            try:
                with open(self.tags_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.tags = set(data.get('tags', []))
                    # 转换标签列表为集合
                    note_tags = data.get('note_tags', {})
                    self.note_tags = {int(note_id): set(tags) for note_id, tags in note_tags.items()}
            except Exception as e:
                print(f"加载标签失败: {e}")
    
    def save_tags(self):
        """
        保存标签到文件
        """
        try:
            data = {
                'tags': list(self.tags),
                'note_tags': {str(note_id): list(tags) for note_id, tags in self.note_tags.items()}
            }
            with open(self.tags_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存标签失败: {e}")

class TagDialog(QDialog):
    """
    标签设置对话框
    """
    def __init__(self, note_id, tag_manager, parent=None):
        super().__init__(parent)
        self.note_id = note_id
        self.tag_manager = tag_manager
        self.note_tags = self.tag_manager.get_tags_for_note(note_id)
        self.all_tags = self.tag_manager.get_all_tags()
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle('管理标签')
        self.setFixedSize(400, 300)
        
        layout = QVBoxLayout()
        
        # 标签输入
        input_layout = QHBoxLayout()
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText('输入新标签...')
        add_btn = QPushButton('添加')
        add_btn.clicked.connect(self.add_tag)
        input_layout.addWidget(self.tag_input)
        input_layout.addWidget(add_btn)
        layout.addLayout(input_layout)
        
        # 便签当前标签
        current_tags_group = QVBoxLayout()
        current_tags_label = QLabel('当前标签:')
        current_tags_group.addWidget(current_tags_label)
        
        self.current_tags_list = QListWidget()
        for tag in self.note_tags:
            item = QListWidgetItem(tag)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.current_tags_list.addItem(item)
        current_tags_group.addWidget(self.current_tags_list)
        layout.addLayout(current_tags_group)
        
        # 可用标签
        available_tags_group = QVBoxLayout()
        available_tags_label = QLabel('可用标签:')
        available_tags_group.addWidget(available_tags_label)
        
        self.available_tags_list = QListWidget()
        for tag in self.all_tags:
            if tag not in self.note_tags:
                item = QListWidgetItem(tag)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.available_tags_list.addItem(item)
        available_tags_group.addWidget(self.available_tags_list)
        layout.addLayout(available_tags_group)
        
        # 按钮
        button_layout = QHBoxLayout()
        save_btn = QPushButton('保存')
        save_btn.clicked.connect(self.save_tags)
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def add_tag(self):
        """
        添加新标签
        """
        tag = self.tag_input.text().strip()
        if tag:
            # 检查标签是否已存在
            if tag in self.all_tags:
                QMessageBox.warning(self, '标签已存在', '此标签已存在，请选择其他名称')
                return
            
            # 添加到可用标签列表
            item = QListWidgetItem(tag)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.available_tags_list.addItem(item)
            
            # 清空输入框
            self.tag_input.clear()
    
    def save_tags(self):
        """
        保存标签设置
        """
        # 处理当前标签列表
        for i in range(self.current_tags_list.count()):
            item = self.current_tags_list.item(i)
            tag = item.text()
            if item.checkState() == Qt.Unchecked:
                # 移除未选中的标签
                self.tag_manager.remove_tag_from_note(self.note_id, tag)
        
        # 处理可用标签列表
        for i in range(self.available_tags_list.count()):
            item = self.available_tags_list.item(i)
            tag = item.text()
            if item.checkState() == Qt.Checked:
                # 添加选中的标签
                self.tag_manager.add_tag_to_note(self.note_id, tag)
        
        QMessageBox.information(self, '保存成功', '标签已保存')
        self.accept()

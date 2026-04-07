import os
import json
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QCheckBox, QDateTimeEdit
)
from PyQt5.QtCore import Qt, QDateTime
from core.sticky_note import StickyNote

class TrashManager:
    """便签回收站管理器"""
    
    def __init__(self, manager):
        self.manager = manager
        self.trash_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'trash')
        os.makedirs(self.trash_dir, exist_ok=True)
    
    def move_to_trash(self, note_id, note_data):
        """将便签移动到回收站
        
        Args:
            note_id: 便签ID
            note_data: 便签数据
        """
        # 添加删除时间戳
        trash_data = {
            'original_id': note_id,
            'note_data': note_data,
            'deleted_at': QDateTime.currentDateTime().toString(Qt.ISODate)
        }
        
        # 生成回收站文件名
        trash_file = os.path.join(self.trash_dir, f'trash_{note_id}_{QDateTime.currentDateTime().toSecsSinceEpoch()}.json')
        
        # 保存到回收站
        try:
            with open(trash_file, 'w', encoding='utf-8') as f:
                json.dump(trash_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f'移动到回收站失败: {e}')
            return False
    
    def get_trash_list(self):
        """获取回收站中的便签列表
        
        Returns:
            list: 回收站中的便签列表
        """
        trash_list = []
        
        for filename in os.listdir(self.trash_dir):
            if filename.startswith('trash_') and filename.endswith('.json'):
                try:
                    file_path = os.path.join(self.trash_dir, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        trash_data = json.load(f)
                        trash_data['trash_file'] = file_path
                        trash_list.append(trash_data)
                except Exception as e:
                    print(f'读取回收站文件失败: {e}')
        
        # 按删除时间排序（最新的在前）
        trash_list.sort(key=lambda x: x['deleted_at'], reverse=True)
        return trash_list
    
    def restore_note(self, trash_file):
        """恢复便签
        
        Args:
            trash_file: 回收站文件路径
        
        Returns:
            int: 恢复的便签ID，失败返回None
        """
        try:
            with open(trash_file, 'r', encoding='utf-8') as f:
                trash_data = json.load(f)
            
            # 生成新的便签ID
            new_id = self.manager.generate_note_id()
            
            # 创建便签
            note_data = trash_data['note_data']
            new_note = StickyNote(
                new_id,
                self.manager.notes_dir,
                manager=self.manager,
                theme_css=self.manager.get_default_theme_css()
            )
            
            # 复制数据
            new_note.note_data = note_data
            new_note.title_edit.setText(note_data.get('title', f'便签 {new_id}'))
            
            content = note_data.get('content', '')
            if content and (content.startswith('<!DOCTYPE') or '<html>' in content):
                new_note.text_edit.setHtml(content)
            else:
                new_note.text_edit.setText(content)
            
            # 保存便签
            new_note.save_note()
            new_note.show()
            
            # 添加到管理器
            self.manager.notes[new_id] = new_note
            self.manager.update_tray_menu()
            
            # 删除回收站文件
            os.remove(trash_file)
            
            return new_id
        except Exception as e:
            print(f'恢复便签失败: {e}')
            return None
    
    def delete_permanently(self, trash_file):
        """永久删除便签
        
        Args:
            trash_file: 回收站文件路径
        
        Returns:
            bool: 是否成功删除
        """
        try:
            os.remove(trash_file)
            return True
        except Exception as e:
            print(f'永久删除失败: {e}')
            return False
    
    def empty_trash(self):
        """清空回收站
        
        Returns:
            int: 删除的文件数量
        """
        count = 0
        for filename in os.listdir(self.trash_dir):
            if filename.startswith('trash_') and filename.endswith('.json'):
                try:
                    file_path = os.path.join(self.trash_dir, filename)
                    os.remove(file_path)
                    count += 1
                except Exception as e:
                    print(f'删除文件失败: {e}')
        return count
    
    def show_trash_dialog(self):
        """显示回收站对话框"""
        dialog = TrashDialog(self.manager, self)
        dialog.exec_()


class TrashDialog(QDialog):
    """回收站对话框"""
    
    def __init__(self, manager, trash_manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.trash_manager = trash_manager
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle('回收站')
        self.setFixedSize(600, 500)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        
        # 说明
        layout.addWidget(QLabel('已删除的便签列表:'))
        
        # 便签列表
        self.trash_list = QListWidget()
        self.trash_list.setSelectionMode(QListWidget.MultiSelection)
        self._populate_trash_list()
        layout.addWidget(self.trash_list)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 全选按钮
        select_all_btn = QPushButton('全选')
        select_all_btn.clicked.connect(self._select_all)
        button_layout.addWidget(select_all_btn)
        
        # 恢复按钮
        restore_btn = QPushButton('恢复选中')
        restore_btn.clicked.connect(self._restore_selected)
        button_layout.addWidget(restore_btn)
        
        # 永久删除按钮
        delete_btn = QPushButton('永久删除')
        delete_btn.clicked.connect(self._delete_selected)
        button_layout.addWidget(delete_btn)
        
        # 清空回收站按钮
        empty_btn = QPushButton('清空回收站')
        empty_btn.clicked.connect(self._empty_trash)
        button_layout.addWidget(empty_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # 关闭按钮
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_btn = QPushButton('关闭')
        close_btn.clicked.connect(self.close)
        close_layout.addWidget(close_btn)
        layout.addLayout(close_layout)
        
        self.setLayout(layout)
    
    def _populate_trash_list(self):
        """填充回收站列表"""
        self.trash_list.clear()
        trash_list = self.trash_manager.get_trash_list()
        
        for trash_data in trash_list:
            note_data = trash_data['note_data']
            title = note_data.get('title', f'便签 {trash_data["original_id"]}')
            deleted_at = QDateTime.fromString(trash_data['deleted_at'], Qt.ISODate)
            display_text = f'{title} - {deleted_at.toString("yyyy-MM-dd HH:mm:ss")}'
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, trash_data['trash_file'])
            self.trash_list.addItem(item)
    
    def _select_all(self):
        """全选"""
        for i in range(self.trash_list.count()):
            item = self.trash_list.item(i)
            item.setSelected(True)
    
    def _restore_selected(self):
        """恢复选中的便签"""
        selected_items = self.trash_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, '警告', '请先选择要恢复的便签')
            return
        
        count = 0
        for item in selected_items:
            trash_file = item.data(Qt.UserRole)
            if self.trash_manager.restore_note(trash_file):
                count += 1
        
        if count > 0:
            QMessageBox.information(self, '恢复成功', f'成功恢复 {count} 个便签')
            self._populate_trash_list()
        else:
            QMessageBox.warning(self, '恢复失败', '没有成功恢复任何便签')
    
    def _delete_selected(self):
        """永久删除选中的便签"""
        selected_items = self.trash_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, '警告', '请先选择要删除的便签')
            return
        
        reply = QMessageBox.question(
            self,
            '确认删除',
            f'确定要永久删除 {len(selected_items)} 个便签吗？\n此操作不可恢复！',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            count = 0
            for item in selected_items:
                trash_file = item.data(Qt.UserRole)
                if self.trash_manager.delete_permanently(trash_file):
                    count += 1
            
            if count > 0:
                QMessageBox.information(self, '删除成功', f'成功永久删除 {count} 个便签')
                self._populate_trash_list()
            else:
                QMessageBox.warning(self, '删除失败', '没有成功删除任何便签')
    
    def _empty_trash(self):
        """清空回收站"""
        if self.trash_list.count() == 0:
            QMessageBox.information(self, '提示', '回收站已经是空的')
            return
        
        reply = QMessageBox.question(
            self,
            '确认清空',
            '确定要清空回收站吗？\n此操作不可恢复！',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            count = self.trash_manager.empty_trash()
            QMessageBox.information(self, '清空成功', f'成功清空回收站，删除了 {count} 个便签')
            self._populate_trash_list()

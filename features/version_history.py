import os
import json
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QTextEdit
)
from PyQt5.QtCore import Qt, QDateTime

class VersionHistoryManager:
    """便签版本历史管理器"""
    
    def __init__(self, manager):
        self.manager = manager
        self.history_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'history')
        os.makedirs(self.history_dir, exist_ok=True)
    
    def get_note_history_dir(self, note_id):
        """获取便签历史目录"""
        return os.path.join(self.history_dir, f'note_{note_id}')
    
    def save_version(self, note_id, note_data, version_note=''):
        """保存便签版本
        
        Args:
            note_id: 便签ID
            note_data: 便签数据
            version_note: 版本说明
        """
        # 创建便签历史目录
        history_dir = self.get_note_history_dir(note_id)
        os.makedirs(history_dir, exist_ok=True)
        
        # 创建版本数据
        version_data = {
            'version_id': QDateTime.currentDateTime().toSecsSinceEpoch(),
            'note_data': note_data,
            'saved_at': QDateTime.currentDateTime().toString(Qt.ISODate),
            'version_note': version_note
        }
        
        # 保存版本文件
        version_file = os.path.join(history_dir, f'version_{version_data["version_id"]}.json')
        try:
            with open(version_file, 'w', encoding='utf-8') as f:
                json.dump(version_data, f, ensure_ascii=False, indent=2)
            
            # 只保留最近20个版本
            self._cleanup_old_versions(note_id, 20)
            
            return True
        except Exception as e:
            print(f'保存版本失败: {e}')
            return False
    
    def get_version_list(self, note_id):
        """获取便签版本列表
        
        Args:
            note_id: 便签ID
        
        Returns:
            list: 版本列表
        """
        history_dir = self.get_note_history_dir(note_id)
        if not os.path.exists(history_dir):
            return []
        
        version_list = []
        for filename in os.listdir(history_dir):
            if filename.startswith('version_') and filename.endswith('.json'):
                try:
                    file_path = os.path.join(history_dir, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        version_data = json.load(f)
                        version_data['version_file'] = file_path
                        version_list.append(version_data)
                except Exception as e:
                    print(f'读取版本文件失败: {e}')
        
        # 按保存时间排序（最新的在前）
        version_list.sort(key=lambda x: x['saved_at'], reverse=True)
        return version_list
    
    def restore_version(self, note_id, version_file):
        """恢复便签版本
        
        Args:
            note_id: 便签ID
            version_file: 版本文件路径
        
        Returns:
            bool: 是否成功恢复
        """
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                version_data = json.load(f)
            
            # 检查便签是否存在
            if note_id not in self.manager.notes:
                return False
            
            note = self.manager.notes[note_id]
            note_data = version_data['note_data']
            
            # 先保存当前版本
            self.save_version(note_id, note.note_data.copy(), '恢复前的版本')
            
            # 恢复便签数据
            note.note_data = note_data
            note.title_edit.setText(note_data.get('title', f'便签 {note_id}'))
            
            content = note_data.get('content', '')
            if content and (content.startswith('<!DOCTYPE') or '<html>' in content):
                note.text_edit.setHtml(content)
            else:
                note.text_edit.setText(content)
            
            # 保存便签
            note.save_note()
            
            return True
        except Exception as e:
            print(f'恢复版本失败: {e}')
            return False
    
    def delete_version(self, version_file):
        """删除版本
        
        Args:
            version_file: 版本文件路径
        
        Returns:
            bool: 是否成功删除
        """
        try:
            os.remove(version_file)
            return True
        except Exception as e:
            print(f'删除版本失败: {e}')
            return False
    
    def delete_all_versions(self, note_id):
        """删除便签的所有版本
        
        Args:
            note_id: 便签ID
        
        Returns:
            int: 删除的版本数量
        """
        history_dir = self.get_note_history_dir(note_id)
        if not os.path.exists(history_dir):
            return 0
        
        count = 0
        for filename in os.listdir(history_dir):
            if filename.startswith('version_') and filename.endswith('.json'):
                try:
                    file_path = os.path.join(history_dir, filename)
                    os.remove(file_path)
                    count += 1
                except Exception as e:
                    print(f'删除版本文件失败: {e}')
        
        return count
    
    def _cleanup_old_versions(self, note_id, keep_count=20):
        """清理旧版本，只保留指定数量的版本
        
        Args:
            note_id: 便签ID
            keep_count: 保留的版本数量
        """
        version_list = self.get_version_list(note_id)
        if len(version_list) > keep_count:
            for version_data in version_list[keep_count:]:
                self.delete_version(version_data['version_file'])
    
    def show_version_history_dialog(self, note_id):
        """显示版本历史对话框
        
        Args:
            note_id: 便签ID
        """
        dialog = VersionHistoryDialog(self.manager, self, note_id)
        dialog.exec_()


class VersionHistoryDialog(QDialog):
    """版本历史对话框"""
    
    def __init__(self, manager, version_history_manager, note_id, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.version_history_manager = version_history_manager
        self.note_id = note_id
        self.current_version_file = None
        self.initUI()
    
    def initUI(self):
        note = self.manager.notes.get(self.note_id)
        title = note.note_data.get('title', f'便签 {self.note_id}') if note else f'便签 {self.note_id}'
        
        self.setWindowTitle(f'版本历史 - {title}')
        self.setFixedSize(800, 600)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        
        main_layout = QHBoxLayout()
        
        # 左侧：版本列表
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel('版本列表:'))
        
        self.version_list = QListWidget()
        self.version_list.itemClicked.connect(self._on_version_selected)
        self._populate_version_list()
        left_layout.addWidget(self.version_list)
        
        # 删除版本按钮
        delete_btn = QPushButton('删除版本')
        delete_btn.clicked.connect(self._delete_version)
        left_layout.addWidget(delete_btn)
        
        main_layout.addLayout(left_layout, 1)
        
        # 右侧：版本预览
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel('版本预览:'))
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        right_layout.addWidget(self.preview_text)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        restore_btn = QPushButton('恢复此版本')
        restore_btn.clicked.connect(self._restore_version)
        button_layout.addWidget(restore_btn)
        
        close_btn = QPushButton('关闭')
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        
        right_layout.addLayout(button_layout)
        
        main_layout.addLayout(right_layout, 2)
        
        self.setLayout(main_layout)
    
    def _populate_version_list(self):
        """填充版本列表"""
        self.version_list.clear()
        version_list = self.version_history_manager.get_version_list(self.note_id)
        
        for version_data in version_list:
            saved_at = QDateTime.fromString(version_data['saved_at'], Qt.ISODate)
            version_note = version_data.get('version_note', '')
            display_text = saved_at.toString('yyyy-MM-dd HH:mm:ss')
            if version_note:
                display_text += f' - {version_note}'
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, version_data['version_file'])
            self.version_list.addItem(item)
    
    def _on_version_selected(self, item):
        """版本选中时显示预览"""
        version_file = item.data(Qt.UserRole)
        self.current_version_file = version_file
        
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                version_data = json.load(f)
            
            note_data = version_data['note_data']
            title = note_data.get('title', '')
            content = note_data.get('plain_content', note_data.get('content', ''))
            
            preview_text = f'标题: {title}\n\n'
            preview_text += '=' * 50 + '\n\n'
            preview_text += content
            
            self.preview_text.setText(preview_text)
        except Exception as e:
            self.preview_text.setText(f'读取版本失败: {e}')
    
    def _restore_version(self):
        """恢复选中的版本"""
        if not self.current_version_file:
            QMessageBox.warning(self, '警告', '请先选择一个版本')
            return
        
        reply = QMessageBox.question(
            self,
            '确认恢复',
            '确定要恢复到此版本吗？\n当前版本将被保存。',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if self.version_history_manager.restore_version(self.note_id, self.current_version_file):
                QMessageBox.information(self, '恢复成功', '便签已成功恢复到该版本')
                self._populate_version_list()
                self.preview_text.clear()
                self.current_version_file = None
            else:
                QMessageBox.warning(self, '恢复失败', '恢复版本失败')
    
    def _delete_version(self):
        """删除选中的版本"""
        current_item = self.version_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, '警告', '请先选择一个版本')
            return
        
        reply = QMessageBox.question(
            self,
            '确认删除',
            '确定要删除此版本吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            version_file = current_item.data(Qt.UserRole)
            if self.version_history_manager.delete_version(version_file):
                QMessageBox.information(self, '删除成功', '版本已删除')
                self._populate_version_list()
                self.preview_text.clear()
                self.current_version_file = None
            else:
                QMessageBox.warning(self, '删除失败', '删除版本失败')

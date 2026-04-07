import json
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QFileDialog, QMessageBox, QListWidget,
    QListWidgetItem, QCheckBox
)
from PyQt5.QtCore import Qt

class ExportImportManager:
    """导出/导入管理器"""
    
    def __init__(self, manager):
        self.manager = manager
    
    def show_export_dialog(self):
        """显示导出对话框"""
        dialog = ExportDialog(self.manager)
        dialog.exec_()
    
    def show_import_dialog(self):
        """显示导入对话框"""
        dialog = ImportDialog(self.manager)
        dialog.exec_()
    
    def export_note(self, note_id, format='json', output_path=None):
        """导出单个便签
        
        Args:
            note_id: 便签ID
            format: 导出格式 (json, markdown, txt)
            output_path: 输出路径，如果为None则自动生成
        
        Returns:
            str: 导出的文件路径
        """
        if note_id not in self.manager.notes:
            return None
        
        note = self.manager.notes[note_id]
        note_data = note.note_data.copy()
        
        if output_path is None:
            # 生成默认文件名
            title = note_data.get('title', f'note_{note_id}')
            safe_title = ''.join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
            if not safe_title:
                safe_title = f'note_{note_id}'
            output_path = f'{safe_title}.{format}'
        
        # 根据格式导出
        if format == 'json':
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(note_data, f, ensure_ascii=False, indent=2)
        elif format == 'markdown':
            self._export_as_markdown(note_data, output_path)
        elif format == 'txt':
            self._export_as_txt(note_data, output_path)
        
        return output_path
    
    def export_all_notes(self, format='json', output_dir=None):
        """导出所有便签
        
        Args:
            format: 导出格式
            output_dir: 输出目录
        
        Returns:
            list: 导出的文件路径列表
        """
        if output_dir is None:
            output_dir = 'exported_notes'
        
        os.makedirs(output_dir, exist_ok=True)
        
        exported_files = []
        for note_id in self.manager.notes:
            title = self.manager.notes[note_id].note_data.get('title', f'note_{note_id}')
            safe_title = ''.join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
            if not safe_title:
                safe_title = f'note_{note_id}'
            output_path = os.path.join(output_dir, f'{safe_title}.{format}')
            
            try:
                result = self.export_note(note_id, format, output_path)
                if result:
                    exported_files.append(result)
            except Exception as e:
                print(f'导出便签 {note_id} 失败: {e}')
        
        return exported_files
    
    def import_notes(self, file_paths):
        """导入便签
        
        Args:
            file_paths: 文件路径列表
        
        Returns:
            list: 导入的便签ID列表
        """
        imported_ids = []
        
        for file_path in file_paths:
            try:
                note_id = self._import_single_note(file_path)
                if note_id:
                    imported_ids.append(note_id)
            except Exception as e:
                print(f'导入文件 {file_path} 失败: {e}')
        
        return imported_ids
    
    def _export_as_markdown(self, note_data, output_path):
        """导出为Markdown格式"""
        title = note_data.get('title', 'Untitled')
        content = note_data.get('plain_content', note_data.get('content', ''))
        tags = note_data.get('tags', [])
        group = note_data.get('group', '')
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f'# {title}\n\n')
            
            if tags:
                f.write('**标签:** ' + ', '.join(f'#{tag}' for tag in tags) + '\n\n')
            
            if group:
                f.write(f'**分组:** {group}\n\n')
            
            f.write('---\n\n')
            f.write(content)
    
    def _export_as_txt(self, note_data, output_path):
        """导出为纯文本格式"""
        title = note_data.get('title', 'Untitled')
        content = note_data.get('plain_content', note_data.get('content', ''))
        tags = note_data.get('tags', [])
        group = note_data.get('group', '')
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f'{title}\n')
            f.write('=' * len(title) + '\n\n')
            
            if tags:
                f.write('标签: ' + ', '.join(tags) + '\n\n')
            
            if group:
                f.write(f'分组: {group}\n\n')
            
            f.write(content)
    
    def _import_single_note(self, file_path):
        """导入单个便签文件"""
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.json':
            return self._import_from_json(file_path)
        else:
            # 其他格式创建新便签
            return self._import_from_text(file_path)
    
    def _import_from_json(self, file_path):
        """从JSON文件导入"""
        with open(file_path, 'r', encoding='utf-8') as f:
            note_data = json.load(f)
        
        # 生成新的便签ID
        new_id = self.manager.generate_note_id()
        
        # 创建便签
        from core.sticky_note import StickyNote
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
        
        return new_id
    
    def _import_from_text(self, file_path):
        """从文本文件导入（markdown或txt）"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 从文件名获取标题
        filename = os.path.basename(file_path)
        title = os.path.splitext(filename)[0]
        
        # 创建新便签
        new_id = self.manager.generate_note_id()
        from core.sticky_note import StickyNote
        new_note = StickyNote(
            new_id, 
            self.manager.notes_dir, 
            manager=self.manager,
            theme_css=self.manager.get_default_theme_css()
        )
        
        new_note.title_edit.setText(title)
        new_note.text_edit.setText(content)
        new_note.save_note()
        new_note.show()
        
        # 添加到管理器
        self.manager.notes[new_id] = new_note
        self.manager.update_tray_menu()
        
        return new_id


class ExportDialog(QDialog):
    """导出对话框"""
    
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.export_import_manager = ExportImportManager(manager)
        self.selected_notes = set()
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle('导出便签')
        self.setFixedSize(500, 400)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        
        # 便签选择
        layout.addWidget(QLabel('选择要导出的便签:'))
        
        self.note_list = QListWidget()
        self.note_list.setSelectionMode(QListWidget.MultiSelection)
        self._populate_note_list()
        layout.addWidget(self.note_list)
        
        # 全选按钮
        select_all_btn = QPushButton('全选')
        select_all_btn.clicked.connect(self._select_all)
        layout.addWidget(select_all_btn)
        
        # 导出格式选择
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel('导出格式:'))
        self.format_combo = QComboBox()
        self.format_combo.addItems(['JSON', 'Markdown', 'TXT'])
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        layout.addLayout(format_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        export_btn = QPushButton('导出')
        export_btn.clicked.connect(self._do_export)
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.close)
        
        button_layout.addStretch()
        button_layout.addWidget(export_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def _populate_note_list(self):
        """填充便签列表"""
        self.note_list.clear()
        for note_id, note in sorted(self.manager.notes.items()):
            title = note.note_data.get('title', f'便签 {note_id}')
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, note_id)
            self.note_list.addItem(item)
    
    def _select_all(self):
        """全选"""
        for i in range(self.note_list.count()):
            item = self.note_list.item(i)
            item.setSelected(True)
    
    def _do_export(self):
        """执行导出"""
        selected_items = self.note_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, '警告', '请至少选择一个便签')
            return
        
        # 选择输出目录
        output_dir = QFileDialog.getExistingDirectory(self, '选择输出目录')
        if not output_dir:
            return
        
        # 获取导出格式
        format = self.format_combo.currentText().lower()
        
        # 导出便签
        exported_count = 0
        for item in selected_items:
            note_id = item.data(Qt.UserRole)
            try:
                self.export_import_manager.export_note(note_id, format, output_dir)
                exported_count += 1
            except Exception as e:
                QMessageBox.warning(self, '导出错误', f'导出便签失败: {e}')
        
        if exported_count > 0:
            QMessageBox.information(self, '导出成功', f'成功导出 {exported_count} 个便签到 {output_dir}')
            self.close()


class ImportDialog(QDialog):
    """导入对话框"""
    
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.export_import_manager = ExportImportManager(manager)
        self.file_paths = []
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle('导入便签')
        self.setFixedSize(500, 400)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        
        # 说明
        layout.addWidget(QLabel('选择要导入的便签文件（支持JSON、Markdown、TXT）:'))
        
        # 文件列表
        self.file_list = QListWidget()
        layout.addWidget(self.file_list)
        
        # 选择文件按钮
        select_files_btn = QPushButton('选择文件')
        select_files_btn.clicked.connect(self._select_files)
        layout.addWidget(select_files_btn)
        
        # 按钮
        button_layout = QHBoxLayout()
        import_btn = QPushButton('导入')
        import_btn.clicked.connect(self._do_import)
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.close)
        
        button_layout.addStretch()
        button_layout.addWidget(import_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def _select_files(self):
        """选择文件"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            '选择便签文件',
            '',
            '便签文件 (*.json *.md *.txt);;所有文件 (*.*)'
        )
        
        if files:
            self.file_paths = files
            self.file_list.clear()
            for file_path in files:
                self.file_list.addItem(os.path.basename(file_path))
    
    def _do_import(self):
        """执行导入"""
        if not self.file_paths:
            QMessageBox.warning(self, '警告', '请先选择要导入的文件')
            return
        
        try:
            imported_ids = self.export_import_manager.import_notes(self.file_paths)
            if imported_ids:
                QMessageBox.information(self, '导入成功', f'成功导入 {len(imported_ids)} 个便签')
                self.close()
            else:
                QMessageBox.warning(self, '导入失败', '没有成功导入任何便签')
        except Exception as e:
            QMessageBox.warning(self, '导入错误', f'导入便签失败: {e}')

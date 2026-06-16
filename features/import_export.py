# -*- coding: utf-8 -*-
"""
便签导入导出功能模块

支持：
- 单便签导出为 TXT / Markdown
- 批量导出所有便签为 ZIP 或目录
- 从 TXT 文件导入创建便签
- 批量导入
"""

import os
import json
import zipfile
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QRadioButton, QGroupBox, QCheckBox, QProgressBar,
    QButtonGroup
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal


class ExportWorker(QThread):
    """导出工作线程"""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, export_items, output_dir, export_format='txt'):
        super().__init__()
        self.export_items = export_items  # [(note_id, title, content), ...]
        self.output_dir = output_dir
        self.export_format = export_format

    def run(self):
        try:
            total = len(self.export_items)
            filenames = []
            for i, (note_id, title, content) in enumerate(self.export_items):
                safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
                if not safe_title:
                    safe_title = f'note_{note_id}'
                ext = '.md' if self.export_format == 'markdown' else '.txt'
                filepath = os.path.join(self.output_dir, f'{safe_title}{ext}')
                # 防止重名
                counter = 1
                while os.path.exists(filepath):
                    filepath = os.path.join(self.output_dir, f'{safe_title}_{counter}{ext}')
                    counter += 1
                with open(filepath, 'w', encoding='utf-8') as f:
                    if self.export_format == 'markdown':
                        f.write(f'# {title}\n\n')
                        f.write(f'> 便签 ID: {note_id}\n\n')
                        f.write(content)
                    else:
                        f.write(f'{title}\n{"=" * len(title)}\n\n')
                        f.write(content)
                filenames.append(filepath)
                self.progress.emit(int((i + 1) / total * 100), f'{i+1}/{total}')

            # 如果是批量，打 ZIP
            if len(self.export_items) > 1:
                zip_name = f'sticky_notes_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
                zip_path = os.path.join(self.output_dir, zip_name)
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for fp in filenames:
                        zf.write(fp, os.path.basename(fp))
                # 删除临时文件
                for fp in filenames:
                    os.remove(fp)
                self.finished.emit(zip_path)
            else:
                self.finished.emit(filenames[0])
        except Exception as e:
            self.failed.emit(str(e))


class ImportExportDialog(QDialog):
    """导入导���对话框"""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle('导入导出')
        self.setFixedSize(500, 450)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.initUI()
        # 应用主题适配
        try:
            from features.theme_helper import apply_dialog_theme, get_current_theme_css
            apply_dialog_theme(self, get_current_theme_css(manager))
        except Exception:
            pass

    def initUI(self):
        layout = QVBoxLayout()

        # 导出区域
        export_group = QGroupBox('导出便签')
        export_layout = QVBoxLayout()

        # 格式选择
        fmt_layout = QHBoxLayout()
        self.format_group = QButtonGroup(self)
        self.txt_radio = QRadioButton('纯文本 (.txt)')
        self.txt_radio.setChecked(True)
        self.md_radio = QRadioButton('Markdown (.md)')
        self.format_group.addButton(self.txt_radio, 1)
        self.format_group.addButton(self.md_radio, 2)
        fmt_layout.addWidget(self.txt_radio)
        fmt_layout.addWidget(self.md_radio)
        fmt_layout.addStretch()
        export_layout.addLayout(fmt_layout)

        # 便签选择
        self.export_list = QListWidget()
        self.export_list.setSelectionMode(QListWidget.ExtendedSelection)
        for note_id, note in sorted(self.manager.notes.items()):
            title = note.note_data.get('title', f'便签 {note_id}')
            item = QListWidgetItem(f'{title}')
            item.setData(Qt.UserRole, note_id)
            self.export_list.addItem(item)
        export_layout.addWidget(QLabel('选择要导出的便签（可多选）：'))
        export_layout.addWidget(self.export_list)

        # 全选按钮
        select_layout = QHBoxLayout()
        all_btn = QPushButton('全选')
        all_btn.clicked.connect(self.export_list.selectAll)
        none_btn = QPushButton('取消全选')
        none_btn.clicked.connect(self.export_list.clearSelection)
        select_layout.addWidget(all_btn)
        select_layout.addWidget(none_btn)
        select_layout.addStretch()
        export_layout.addLayout(select_layout)

        # 导出按钮
        export_btn = QPushButton('导出选中便签')
        export_btn.clicked.connect(self.export_notes)
        export_layout.addWidget(export_btn)

        self.export_progress = QProgressBar()
        self.export_progress.setVisible(False)
        export_layout.addWidget(self.export_progress)

        self.export_status = QLabel('')
        export_layout.addWidget(self.export_status)

        export_group.setLayout(export_layout)
        layout.addWidget(export_group)

        # 导入区域
        import_group = QGroupBox('导入便签')
        import_layout = QVBoxLayout()

        import_btn = QPushButton('从 TXT 文件导入...')
        import_btn.clicked.connect(self.import_notes)
        import_layout.addWidget(import_btn)

        self.import_status = QLabel('')
        import_layout.addWidget(self.import_status)

        import_group.setLayout(import_layout)
        layout.addWidget(import_group)

        # 关闭
        close_btn = QPushButton('关闭')
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)

    def export_notes(self):
        selected = self.export_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, '提示', '请选择要导出的便签')
            return

        output_dir = QFileDialog.getExistingDirectory(self, '选择导出目录')
        if not output_dir:
            return

        fmt = 'markdown' if self.md_radio.isChecked() else 'txt'
        items = []
        for item in selected:
            note_id = item.data(Qt.UserRole)
            note = self.manager.notes.get(note_id)
            if note:
                title = note.note_data.get('title', f'便签 {note_id}')
                content = note.text_edit.toPlainText()
                items.append((note_id, title, content))

        self.export_progress.setVisible(True)
        self.export_progress.setValue(0)
        self.worker = ExportWorker(items, output_dir, fmt)
        self.worker.progress.connect(lambda v, m: (
            self.export_progress.setValue(v),
            self.export_status.setText(f'导出中: {m}')
        ))
        self.worker.finished.connect(self._on_export_finished)
        self.worker.failed.connect(self._on_export_failed)
        self.worker.start()

    def _on_export_finished(self, path):
        self.export_progress.setValue(100)
        self.export_status.setText(f'✅ 导出成功: {path}')
        QMessageBox.information(self, '导出完成', f'已导出到:\n{path}')

    def _on_export_failed(self, error):
        self.export_status.setText(f'❌ 导出失败: {error}')
        QMessageBox.critical(self, '导出失败', error)

    def import_notes(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, '选择 TXT 文件', '',
            '文本文件 (*.txt);;所有文件 (*.*)'
        )
        if not filepaths:
            return

        count = 0
        for fp in filepaths:
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    content = f.read()
                # 第一行作为标题
                lines = content.split('\n')
                title = lines[0].strip()[:50] if lines else os.path.basename(fp)
                # 移除可能的标题分隔线
                if len(lines) > 1 and all(c in '=-' for c in lines[1]):
                    body = '\n'.join(lines[2:])
                else:
                    body = '\n'.join(lines[1:]) if len(lines) > 1 else ''
                self.manager.add_note()
                # 获取刚创建的便签（最大 ID）
                if self.manager.notes:
                    max_id = max(self.manager.notes.keys())
                    new_note = self.manager.notes[max_id]
                    new_note.title_edit.setText(title)
                    new_note.text_edit.setPlainText(body.strip())
                    new_note.note_data['title'] = title
                    new_note.note_data['content'] = body.strip()
                    new_note.save_note()
                    count += 1
            except Exception as e:
                QMessageBox.warning(self, '导入失败', f'导入 {os.path.basename(fp)} 失败:\n{e}')

        self.import_status.setText(f'✅ 成功导入 {count} 个便签')
        self.manager.update_tray_menu()
        if count > 0:
            QMessageBox.information(self, '导入完成', f'已从 {len(filepaths)} 个文件导入 {count} 个便签')

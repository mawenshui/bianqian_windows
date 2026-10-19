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
from features.search import _plain_content


def format_checklist(checklist, markdown=False):
    """为文本导出和预览生成清单，正文始终保持独立。"""
    lines = []
    for entry in checklist if isinstance(checklist, list) else []:
        if isinstance(entry, dict):
            text = str(entry.get('text', '')).strip()
            if text:
                mark = 'x' if entry.get('done') else ' '
                lines.append(f'- [{mark}] {text}' if markdown else
                             f'{"☑" if entry.get("done") else "☐"} {text}')
    return '\n'.join(lines)


def preview_txt_import(filepaths, existing_notes):
    """读取导入文件并标记重复项；读取失败不会阻止其他文件。"""
    existing = {
        (str(data.get('title', '')).strip(), _plain_content(data).strip())
        for data in existing_notes
    }
    entries = []
    errors = []
    for path in filepaths:
        try:
            with open(path, 'r', encoding='utf-8') as stream:
                text = stream.read()
            lines = text.splitlines()
            title = (lines[0].strip()[:50] if lines else '') or os.path.basename(path)
            if len(lines) > 1 and lines[1] and all(char in '=-' for char in lines[1]):
                body = '\n'.join(lines[2:]).strip()
            else:
                body = '\n'.join(lines[1:]).strip()
            fingerprint = (title, body)
            entries.append({
                'path': path, 'title': title, 'body': body,
                'duplicate': fingerprint in existing,
            })
            existing.add(fingerprint)
        except (OSError, UnicodeError) as exc:
            errors.append(f'{os.path.basename(path)}: {exc}')
    return entries, errors


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
            for i, entry in enumerate(self.export_items):
                note_id, title, content = entry[:3]
                checklist = entry[3] if len(entry) > 3 else []
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
                        checklist_text = format_checklist(checklist, True)
                        if checklist_text:
                            f.write(f'\n\n## 清单\n\n{checklist_text}\n')
                    else:
                        f.write(f'{title}\n{"=" * len(title)}\n\n')
                        f.write(content)
                        checklist_text = format_checklist(checklist)
                        if checklist_text:
                            f.write(f'\n\n清单\n{checklist_text}\n')
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
        self.resize(560, 640)
        self.setMinimumSize(500, 550)
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

        transfer_group = QGroupBox('本地迁移包（保留便签全部字段与引用资源）')
        transfer_layout = QVBoxLayout()
        transfer_layout.addWidget(QLabel('迁移包为明文 ZIP；默认不包含密码、同步配置和历史。'))
        transfer_export = QPushButton('导出可迁移包...')
        transfer_export.clicked.connect(self.export_transfer_package)
        transfer_layout.addWidget(transfer_export)
        transfer_import = QPushButton('导入可迁移包...')
        transfer_import.clicked.connect(self.import_transfer_package)
        transfer_layout.addWidget(transfer_import)
        transfer_group.setLayout(transfer_layout)
        layout.addWidget(transfer_group)

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

    def export_transfer_package(self):
        from features.transfer_package import TransferPackageService
        path, _ = QFileDialog.getSaveFileName(
            self, '导出可迁移包', 'StickyNote_transfer.zip', 'ZIP 文件 (*.zip)')
        if not path:
            return
        try:
            self.manager.backup_manager.flush_open_notes()
            result = TransferPackageService(self.manager.notes_dir).export_package(path)
            if not result['valid']:
                raise ValueError('; '.join(result['errors']))
        except Exception as exc:
            QMessageBox.warning(self, '导出失败', str(exc))
            return
        QMessageBox.information(self, '导出完成',
            f'已导出 {result["note_count"]} 张便签、{result["attachment_count"]} 个附件。\n{path}')

    def import_transfer_package(self):
        from features.transfer_package import TransferPackageService
        path, _ = QFileDialog.getOpenFileName(
            self, '导入可迁移包', '', 'ZIP 文件 (*.zip)')
        if not path:
            return
        service = TransferPackageService(self.manager.notes_dir)
        preview = service.preview_package(path)
        if not preview['valid']:
            QMessageBox.warning(self, '校验失败', '\n'.join(preview['errors']))
            return
        if not preview['destination_empty']:
            QMessageBox.warning(self, '目标库非空', '迁移包只导入空白便签库，请先备份并清理目标库。')
            return
        if QMessageBox.question(self, '确认迁移',
                f'将导入 {preview["note_count"]} 张便签、{preview["attachment_count"]} 个附件。'
                '导入前会保存当前库的安全备份。继续？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.manager.backup_manager.flush_open_notes()
        except Exception as exc:
            QMessageBox.warning(self, '导入未开始', f'便签保存失败，未导入迁移包：{exc}')
            return
        placeholder = service._placeholder()
        placeholder_uuid = None
        if placeholder:
            note_id = int(os.path.basename(placeholder)[5:-5])
            note = self.manager.notes.get(note_id)
            placeholder_uuid = note.note_data.get('note_uuid') if note else None
        def safety_backup():
            backup = self.manager.backup_manager.create_backup()
            return bool(backup and self.manager.backup_manager.preview_backup(backup)['valid'])
        try:
            service.import_package(path, safety_backup=safety_backup)
            if placeholder:
                self.manager._close_note_for_lifecycle(note_id)
                self.manager.history_store.remove_note(placeholder_uuid)
            if self.manager._tag_manager is not None:
                self.manager._tag_manager.tags = self.manager._tag_manager.load_tags()
            self.manager.load_notes()
            self.manager.search_manager.refresh_index()
            self.manager.update_tray_menu()
        except Exception as exc:
            QMessageBox.warning(self, '导入失败', str(exc))
            return
        QMessageBox.information(self, '导入完成', f'成功导入 {preview["note_count"]} 张便签。')

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
                items.append((note_id, title, content,
                              note.note_data.get('checklist', [])))

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

        existing = [note.note_data for note in self.manager.notes.values()]
        for name in os.listdir(self.manager.notes_dir):
            if not (name.startswith('note_') and name.endswith('.json')):
                continue
            try:
                with open(os.path.join(self.manager.notes_dir, name), encoding='utf-8') as stream:
                    existing.append(json.load(stream))
            except (OSError, ValueError):
                continue
        entries, errors = preview_txt_import(filepaths, existing)
        if not entries:
            QMessageBox.warning(self, '导入失败', '\n'.join(errors) or '没有可导入的文件')
            return
        duplicate_count = sum(entry['duplicate'] for entry in entries)
        preview = QMessageBox(self)
        preview.setWindowTitle('导入预览')
        preview.setText(
            f'可读取 {len(entries)} 个文件，其中重复 {duplicate_count} 个。\n'
            f'标题预览：{", ".join(entry["title"] for entry in entries[:5])}\n'
            f'读取失败 {len(errors)} 个。'
        )
        skip_button = preview.addButton('跳过重复并导入', QMessageBox.AcceptRole)
        all_button = preview.addButton('全部导入', QMessageBox.ActionRole)
        preview.addButton('取消', QMessageBox.RejectRole)
        preview.exec_()
        selected = preview.clickedButton()
        if selected not in (skip_button, all_button):
            return
        count = 0
        skipped = 0
        for entry in entries:
            if entry['duplicate'] and selected == skip_button:
                skipped += 1
                continue
            try:
                self.manager.add_note()
                if self.manager.notes:
                    max_id = max(self.manager.notes.keys())
                    new_note = self.manager.notes[max_id]
                    new_note.title_edit.setText(entry['title'])
                    new_note.text_edit.setPlainText(entry['body'])
                    new_note.save_note_sync()
                    count += 1
            except Exception as e:
                errors.append(f'{os.path.basename(entry["path"])}: {e}')

        self.import_status.setText(f'导入 {count} 个，跳过重复 {skipped} 个，失败 {len(errors)} 个')
        self.manager.update_tray_menu()
        QMessageBox.information(
            self, '导入结果',
            f'成功 {count} 个，跳过重复 {skipped} 个，失败 {len(errors)} 个。'
            + ('\n失败详情：\n' + '\n'.join(errors) if errors else '')
        )

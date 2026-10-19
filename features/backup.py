# -*- coding: utf-8 -*-
"""
数据备份功能模块

提供自动和手动备份功能，确保用户数据安全
"""

import os
import json
import shutil
import zipfile
import hashlib
import logging
import tempfile
import uuid
import re
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QFileDialog, QCheckBox, QSpinBox, QGroupBox, QFormLayout
)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont

from core import get_styles_dir, get_user_data_dir

logger = logging.getLogger(__name__)


class BackupWorker(QThread):
    """
    备份工作线程
    
    在后台执行备份操作，避免阻塞UI
    """
    
    progress_updated = pyqtSignal(int)  # 进度更新信号
    backup_completed = pyqtSignal(str)  # 备份完成信号
    backup_failed = pyqtSignal(str)     # 备份失败信号
    
    def __init__(self, backup_manager, backup_name=None):
        """
        初始化备份工作线程
        
        Args:
            backup_manager: 备份管理器实例
            backup_name: 备份名称
        """
        super().__init__()
        self.backup_manager = backup_manager
        self.backup_name = backup_name
    
    def run(self):
        """
        执行备份操作
        """
        try:
            backup_path = self.backup_manager.create_backup_internal(
                self.backup_name, self.progress_updated
            )
            if backup_path:
                self.backup_completed.emit(backup_path)
            else:
                self.backup_failed.emit("备份创建失败")
        except Exception as e:
            self.backup_failed.emit(str(e))


class RestoreWorker(QThread):
    """
    恢复工作线程
    
    在后台执行恢复操作，避免阻塞UI
    """
    
    progress_updated = pyqtSignal(int)  # 进度更新信号
    restore_completed = pyqtSignal()    # 恢复完成信号
    restore_failed = pyqtSignal(str)    # 恢复失败信号
    
    def __init__(self, backup_manager, backup_path):
        """
        初始化恢复工作线程
        
        Args:
            backup_manager: 备份管理器实例
            backup_path: 备份文件路径
        """
        super().__init__()
        self.backup_manager = backup_manager
        self.backup_path = backup_path
    
    def run(self):
        """
        执行恢复操作
        """
        try:
            success = self.backup_manager.restore_backup_internal(
                self.backup_path, self.progress_updated
            )
            if success:
                self.restore_completed.emit()
            else:
                self.restore_failed.emit("恢复操作失败")
        except Exception as e:
            safety = getattr(self.backup_manager, 'last_safety_backup_path', None)
            detail = f'恢复步骤: {e}'
            if safety:
                detail += f'\n恢复前安全备份: {safety}'
            self.restore_failed.emit(detail)


class BackupDialog(QDialog):
    """
    备份管理对话框
    
    提供备份和恢复的图形界面
    """
    
    def __init__(self, backup_manager, parent=None):
        """
        初始化备份对话框
        
        Args:
            backup_manager: 备份管理器实例
            parent: 父窗口
        """
        super().__init__(parent)
        self.backup_manager = backup_manager
        self.backup_worker = None
        self.restore_worker = None
        self.initUI()
        self.refresh_backup_list()
        # 应用主题适配
        try:
            from features.theme_helper import apply_dialog_theme, get_current_theme_css
            manager = getattr(backup_manager, 'manager', None)
            apply_dialog_theme(self, get_current_theme_css(manager))
        except Exception:
            pass
    
    def initUI(self):
        """
        初始化用户界面
        """
        self.setWindowTitle('备份管理')
        self.setFixedSize(600, 500)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        
        # 标题
        title_label = QLabel('数据备份与恢复')
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 备份设置组
        backup_group = QGroupBox('备份设置')
        backup_layout = QFormLayout()
        
        # 自动备份设置
        self.auto_backup_checkbox = QCheckBox('启用自动备份')
        self.auto_backup_checkbox.setChecked(self.backup_manager.auto_backup_enabled)
        self.auto_backup_checkbox.stateChanged.connect(self.on_auto_backup_changed)
        backup_layout.addRow(self.auto_backup_checkbox)
        
        # 备份间隔设置
        interval_layout = QHBoxLayout()
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(1, 24)
        self.interval_spinbox.setValue(self.backup_manager.auto_backup_interval // 3600)
        self.interval_spinbox.setSuffix(' 小时')
        self.interval_spinbox.valueChanged.connect(self.on_interval_changed)
        interval_layout.addWidget(QLabel('备份间隔:'))
        interval_layout.addWidget(self.interval_spinbox)
        interval_layout.addStretch()
        backup_layout.addRow(interval_layout)
        
        # 最大备份数量设置
        max_backup_layout = QHBoxLayout()
        self.max_backup_spinbox = QSpinBox()
        self.max_backup_spinbox.setRange(1, 100)
        self.max_backup_spinbox.setValue(self.backup_manager.max_backup_count)
        self.max_backup_spinbox.setSuffix(' 个')
        self.max_backup_spinbox.valueChanged.connect(self.on_max_backup_changed)
        max_backup_layout.addWidget(QLabel('最大备份数:'))
        max_backup_layout.addWidget(self.max_backup_spinbox)
        max_backup_layout.addStretch()
        backup_layout.addRow(max_backup_layout)
        
        backup_group.setLayout(backup_layout)
        layout.addWidget(backup_group)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        
        self.create_backup_btn = QPushButton('创建备份')
        self.create_backup_btn.clicked.connect(self.create_backup)
        
        self.import_backup_btn = QPushButton('导入备份')
        self.import_backup_btn.clicked.connect(self.import_backup)
        
        self.export_backup_btn = QPushButton('导出备份')
        self.export_backup_btn.clicked.connect(self.export_backup)
        self.export_backup_btn.setEnabled(False)
        
        button_layout.addWidget(self.create_backup_btn)
        button_layout.addWidget(self.import_backup_btn)
        button_layout.addWidget(self.export_backup_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # 备份列表
        list_label = QLabel('现有备份:')
        layout.addWidget(list_label)
        
        self.backup_list = QListWidget()
        self.backup_list.itemSelectionChanged.connect(self.on_backup_selected)
        layout.addWidget(self.backup_list)
        self.preview_label = QLabel('选择备份后显示内容与校验结果')
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 底部按钮
        bottom_layout = QHBoxLayout()
        
        self.restore_btn = QPushButton('恢复选中备份')
        self.restore_btn.clicked.connect(self.restore_backup)
        self.restore_btn.setEnabled(False)
        
        self.delete_btn = QPushButton('删除选中备份')
        self.delete_btn.clicked.connect(self.delete_backup)
        self.delete_btn.setEnabled(False)
        
        self.refresh_btn = QPushButton('刷新列表')
        self.refresh_btn.clicked.connect(self.refresh_backup_list)
        
        self.close_btn = QPushButton('关闭')
        self.close_btn.clicked.connect(self.close)
        
        bottom_layout.addWidget(self.restore_btn)
        bottom_layout.addWidget(self.delete_btn)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.refresh_btn)
        bottom_layout.addWidget(self.close_btn)
        
        layout.addLayout(bottom_layout)
        
        self.setLayout(layout)
    
    def on_auto_backup_changed(self, state):
        """
        处理自动备份设置变化
        
        Args:
            state: 复选框状态
        """
        self.backup_manager.set_auto_backup_enabled(state == Qt.Checked)
    
    def on_interval_changed(self, value):
        """
        处理备份间隔变化
        
        Args:
            value: 间隔值（小时）
        """
        self.backup_manager.set_auto_backup_interval(value * 3600)
    
    def on_max_backup_changed(self, value):
        """
        处理最大备份数量变化
        
        Args:
            value: 最大备份数量
        """
        self.backup_manager.set_max_backup_count(value)
    
    def create_backup(self):
        """
        创建新备份
        """
        try:
            self.backup_manager.flush_open_notes()
        except Exception as exc:
            QMessageBox.warning(self, '备份未开始', f'便签保存失败，未创建备份：{exc}')
            return
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.create_backup_btn.setEnabled(False)
        
        self.backup_worker = BackupWorker(self.backup_manager)
        self.backup_worker.progress_updated.connect(self.progress_bar.setValue)
        self.backup_worker.backup_completed.connect(self.on_backup_completed)
        self.backup_worker.backup_failed.connect(self.on_backup_failed)
        self.backup_worker.start()
    
    def on_backup_completed(self, backup_path):
        """
        处理备份完成事件
        
        Args:
            backup_path: 备份文件路径
        """
        self.progress_bar.setVisible(False)
        self.create_backup_btn.setEnabled(True)
        self.refresh_backup_list()
        QMessageBox.information(self, '备份完成', f'备份已成功创建:\n{backup_path}')
    
    def on_backup_failed(self, error_message):
        """
        处理备份失败事件
        
        Args:
            error_message: 错误消息
        """
        self.progress_bar.setVisible(False)
        self.create_backup_btn.setEnabled(True)
        QMessageBox.warning(self, '备份失败', f'备份创建失败:\n{error_message}')
    
    def import_backup(self):
        """
        导入外部备份文件
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, '选择备份文件', '', 'ZIP文件 (*.zip)'
        )
        
        if file_path:
            try:
                preview = self.backup_manager.preview_backup(file_path)
                if not preview['valid']:
                    raise ValueError('备份校验失败: ' + '; '.join(preview['errors']))
                # 复制文件到备份目录
                backup_name = os.path.basename(file_path)
                if not backup_name.startswith('stickynote_backup_'):
                    backup_name = f"stickynote_backup_imported_{uuid.uuid4().hex[:10]}.zip"
                
                dest_path = os.path.join(self.backup_manager.backup_dir, backup_name)
                if os.path.exists(dest_path):
                    backup_name = f"stickynote_backup_imported_{uuid.uuid4().hex[:10]}.zip"
                    dest_path = os.path.join(self.backup_manager.backup_dir, backup_name)
                shutil.copy2(file_path, dest_path)
                
                self.refresh_backup_list()
                QMessageBox.information(
                    self, '导入成功',
                    f'已导入 {backup_name}\n便签: {preview["note_count"]}，回收站: {preview["trash_count"]}'
                )
                
            except Exception as e:
                QMessageBox.warning(self, '导入失败', f'导入备份文件时出错:\n{e}')
    
    def export_backup(self):
        """
        导出选中的备份文件
        """
        selected_items = self.backup_list.selectedItems()
        if not selected_items:
            return
        
        item = selected_items[0]
        backup_path = item.data(Qt.UserRole)
        backup_name = os.path.basename(backup_path)
        
        if not os.path.exists(backup_path):
            QMessageBox.warning(self, '错误', '备份文件不存在')
            return
        
        save_path, _ = QFileDialog.getSaveFileName(
            self, '保存备份文件', backup_name, 'ZIP文件 (*.zip)'
        )
        
        if save_path:
            try:
                shutil.copy2(backup_path, save_path)
                QMessageBox.information(self, '导出成功', f'备份文件已导出到:\n{save_path}')
            except Exception as e:
                QMessageBox.warning(self, '导出失败', f'导出备份文件时出错:\n{e}')
    
    def restore_backup(self):
        """
        恢复选中的备份
        """
        selected_items = self.backup_list.selectedItems()
        if not selected_items:
            return
        
        item = selected_items[0]
        backup_path = item.data(Qt.UserRole)
        try:
            self.backup_manager.flush_open_notes()
        except Exception as exc:
            QMessageBox.warning(self, '恢复未开始', f'便签保存失败，未恢复备份：{exc}')
            return
        preview = self.backup_manager.preview_backup(backup_path)
        if not preview['valid']:
            QMessageBox.warning(self, '备份不可恢复', '; '.join(preview['errors']))
            return
        reply = QMessageBox.question(
            self, '确认恢复',
            f'备份时间: {preview["created_at"]}\n'
            f'便签: {preview["note_count"]}，回收站: {preview["trash_count"]}，'
            f'主题: {preview["style_count"]}\n'
            f'便签差异: 新增 {preview["new_count"]}、覆盖 {preview["overwrite_count"]}、'
            f'内容相同 {preview["skipped_count"]}、仅当前存在 {preview["removed_count"]}\n'
            f'附件: {preview["attachment_count"]} 个，'
            f'{preview["attachment_bytes"] / 1024 / 1024:.1f} MB\n'
            f'校验: {preview["verification"]} 通过\n\n'
            '恢复前会自动保存当前数据的安全备份。继续恢复吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                self.backup_manager.flush_open_notes()
            except Exception as exc:
                QMessageBox.warning(self, '恢复未开始', f'便签保存失败，未恢复备份：{exc}')
                return
            for note in self.backup_manager.manager.notes.values():
                note.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.restore_btn.setEnabled(False)
            
            self.restore_worker = RestoreWorker(self.backup_manager, backup_path)
            self.restore_worker.progress_updated.connect(self.progress_bar.setValue)
            self.restore_worker.restore_completed.connect(self.on_restore_completed)
            self.restore_worker.restore_failed.connect(self.on_restore_failed)
            self.restore_worker.start()
    
    def on_restore_completed(self):
        """
        处理恢复完成事件
        """
        self.progress_bar.setVisible(False)
        self.restore_btn.setEnabled(True)
        manager = self.backup_manager.manager
        # 旧窗口不可在退出时把恢复后的文件再次覆盖。
        for note in list(manager.notes.values()):
            note._save_timer.stop()
            note.is_deleted = True
            note.close()
        manager.notes.clear()
        manager.search_manager.refresh_index()
        manager.update_tray_menu()
        QMessageBox.information(
            self, '恢复完成', 
            '备份已成功恢复！\n\n请重启应用程序以应用更改。'
        )
    
    def on_restore_failed(self, error_message):
        """
        处理恢复失败事件
        
        Args:
            error_message: 错误消息
        """
        self.progress_bar.setVisible(False)
        self.restore_btn.setEnabled(True)
        for note in self.backup_manager.manager.notes.values():
            note.setEnabled(True)
        QMessageBox.warning(self, '恢复失败', f'恢复备份时出错:\n{error_message}')
    
    def delete_backup(self):
        """
        删除选中的备份
        """
        selected_items = self.backup_list.selectedItems()
        if not selected_items:
            return
        
        reply = QMessageBox.question(
            self, '确认删除', 
            '确定要删除选中的备份吗？此操作不可撤销。',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            item = selected_items[0]
            backup_path = item.data(Qt.UserRole)
            
            try:
                os.remove(backup_path)
                self.refresh_backup_list()
                QMessageBox.information(self, '删除成功', '备份文件已删除')
            except Exception as e:
                QMessageBox.warning(self, '删除失败', f'删除备份文件时出错:\n{e}')
    
    def on_backup_selected(self):
        """
        处理备份选择事件
        """
        has_selection = len(self.backup_list.selectedItems()) > 0
        self.restore_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)
        self.export_backup_btn.setEnabled(has_selection)
        if has_selection:
            path = self.backup_list.selectedItems()[0].data(Qt.UserRole)
            preview = self.backup_manager.preview_backup(path)
            self.preview_label.setText(
                f'时间: {preview["created_at"] or "未知"} · '
                f'便签: {preview["note_count"]} · 回收站: {preview["trash_count"]} · '
                f'主题: {preview["style_count"]} · '
                f'校验: {preview["verification"]} '
                + ('通过' if preview['valid'] else '失败：' + '; '.join(preview['errors']))
                + ('\n标题预览：' + '、'.join(preview['titles']) if preview['titles'] else '')
            )
            self.restore_btn.setEnabled(preview['valid'])
        else:
            self.preview_label.setText('选择备份后显示内容与校验结果')
    
    def refresh_backup_list(self):
        """
        刷新备份列表
        """
        self.backup_list.clear()
        
        backup_files = self.backup_manager.get_backup_list()
        
        for backup_info in backup_files:
            item_text = f"{backup_info['filename']} - {backup_info['date']} ({backup_info['size']})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, backup_info['path'])
            item.setToolTip(f"文件: {backup_info['filename']}\n日期: {backup_info['date']}\n大小: {backup_info['size']}")
            self.backup_list.addItem(item)


class BackupManager:
    """
    备份管理器
    
    管理应用程序的数据备份和恢复功能
    """
    
    def __init__(self, manager):
        """
        初始化备份管理器
        
        Args:
            manager: 便签管理器实例
        """
        self.manager = manager
        self.backup_dir = os.path.join(get_user_data_dir(), 'backups')
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # 备份设置
        self.auto_backup_enabled = True
        self.auto_backup_interval = 3600  # 1小时
        self.max_backup_count = 10
        
        # 自动备份定时器
        self.auto_backup_timer = QTimer()
        self.auto_backup_timer.timeout.connect(self.auto_backup)
        
        # 上次备份时的数据状态哈希（用于跳过无变化的备份）
        self._last_backup_hash = ''
        
        # 加载设置
        self.load_backup_settings()
        
        # 启动自动备份
        if self.auto_backup_enabled:
            self.auto_backup_timer.start(self.auto_backup_interval * 1000)
    
    def create_backup(self, backup_name=None):
        """
        创建备份（公共接口）
        
        Args:
            backup_name: 备份名称，如果为None则使用时间戳
            
        Returns:
            str: 备份文件路径，失败返回None
        """
        self.flush_open_notes()
        return self.create_backup_internal(backup_name)

    def flush_open_notes(self):
        """同步保存所有打开便签，失败时禁止生成可能过时的备份。"""
        for note in list(getattr(self.manager, 'notes', {}).values()):
            worker = getattr(note, '_save_worker', None)
            running = worker is not None and worker.isRunning()
            if running:
                worker.wait()
            if note.save_note_sync() is False:
                raise OSError(f'便签保存失败，备份已停止：{note.note_file}')
    
    def create_backup_internal(self, backup_name=None, progress_callback=None):
        """写入带 SHA256 清单的备份；失败时不留下半成品。"""
        if backup_name is None:
            backup_name = f"stickynote_backup_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}"
        if not re.fullmatch(r'[A-Za-z0-9_-]+', backup_name):
            raise ValueError('备份名称只能包含字母、数字、下划线和连字符')
        backup_path = os.path.join(self.backup_dir, f'{backup_name}.zip')
        files = {}
        for folder, source in (
            ('notes', self.manager.notes_dir),
            ('trash', os.path.join(get_user_data_dir(), 'trash')),
        ):
            if os.path.isdir(source):
                pattern = (r'note_\d+\.json' if folder == 'notes'
                           else r'note_\d+_[0-9a-f]{32}\.json')
                for name in os.listdir(source):
                    if re.fullmatch(pattern, name):
                        files[f'{folder}/{name}'] = os.path.join(source, name)
            images = os.path.join(source, 'images')
            if os.path.isdir(images):
                for name in os.listdir(images):
                    path = os.path.join(images, name)
                    if name not in ('.', '..') and re.fullmatch(r'[A-Za-z0-9_.-]+', name) and os.path.isfile(path):
                        files[f'{folder}/images/{name}'] = path
            attachments = os.path.join(source, 'attachments')
            if os.path.isdir(attachments):
                for note_folder in os.listdir(attachments):
                    valid_folder = (r'note_\d+' if folder == 'notes'
                                    else r'note_\d+_[0-9a-f]{32}')
                    if not re.fullmatch(valid_folder, note_folder):
                        continue
                    root = os.path.join(attachments, note_folder)
                    if os.path.isdir(root):
                        for name in os.listdir(root):
                            path = os.path.join(root, name)
                            if re.fullmatch(r'[0-9a-f]{32}_[^/\\]+', name) and os.path.isfile(path):
                                files[f'{folder}/attachments/{note_folder}/{name}'] = path
            if folder == 'notes':
                conflicts = os.path.join(source, 'conflicts')
                if os.path.isdir(conflicts) and not os.path.islink(conflicts):
                    for name in os.listdir(conflicts):
                        path = os.path.join(conflicts, name)
                        if (re.fullmatch(r'note_[1-9]\d*\.conflict_remote_\d{8}_\d{6}_\d{6}\.json', name)
                                and os.path.isfile(path) and not os.path.islink(path)):
                            files[f'notes/conflicts/{name}'] = path
        if os.path.isfile(self.manager.settings_file):
            files['settings.json'] = self.manager.settings_file
        history_dir = os.path.join(get_user_data_dir(), 'history')
        if os.path.isdir(history_dir):
            key_file = os.path.join(history_dir, 'key.json')
            if os.path.isfile(key_file) and not os.path.islink(key_file):
                files['history/key.json'] = key_file
            for note_uuid in os.listdir(history_dir):
                if not re.fullmatch(r'[0-9a-f]{32}', note_uuid):
                    continue
                folder = os.path.join(history_dir, note_uuid)
                if not os.path.isdir(folder) or os.path.islink(folder):
                    continue
                for name in os.listdir(folder):
                    path = os.path.join(folder, name)
                    if re.fullmatch(r'\d{8}T\d{6}_\d{6}_[0-9a-f]{12}\.snap', name) and os.path.isfile(path) and not os.path.islink(path):
                        files[f'history/{note_uuid}/{name}'] = path
        styles_dir = get_styles_dir()
        if os.path.isdir(styles_dir):
            for name in os.listdir(styles_dir):
                if name.endswith('.css') and os.path.isfile(os.path.join(styles_dir, name)):
                    files[f'styles/{name}'] = os.path.join(styles_dir, name)
        temporary = backup_path + '.tmp'
        manifest = {'format': 1, 'created_at': datetime.now().isoformat(), 'files': {}}
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
                for index, (name, source) in enumerate(sorted(files.items()), 1):
                    with open(source, 'rb') as stream:
                        payload = stream.read()
                    archive.writestr(name, payload)
                    manifest['files'][name] = hashlib.sha256(payload).hexdigest()
                    if progress_callback:
                        progress_callback.emit(int(index / max(len(files), 1) * 95))
                archive.writestr(
                    'manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2)
                )
            os.replace(temporary, backup_path)
            if progress_callback:
                progress_callback.emit(100)
            return backup_path
        except Exception:
            if os.path.exists(temporary):
                os.remove(temporary)
            logger.exception('创建备份失败')
            return None
    
    def preview_backup(self, backup_path):
        """只读校验备份并提供恢复前摘要。兼容无清单的旧备份。"""
        result = {
            'valid': False, 'errors': [], 'note_count': 0, 'trash_count': 0,
            'style_count': 0, 'titles': [], 'created_at': '',
            'verification': 'CRC', 'new_count': 0, 'overwrite_count': 0,
            'skipped_count': 0, 'removed_count': 0,
            'attachment_count': 0, 'attachment_bytes': 0,
        }
        try:
            with zipfile.ZipFile(backup_path) as archive:
                members = [item for item in archive.infolist() if not item.is_dir()]
                names = [item.filename for item in members]
                if len(names) != len(set(names)):
                    result['errors'].append('备份包含重复文件名')
                total_size = sum(item.file_size for item in members)
                if total_size > 512 * 1024 * 1024:
                    result['errors'].append('解压后数据超过 512 MB')
                for name in names:
                    leaf = name.rsplit('/', 1)[-1]
                    if (not leaf or leaf.endswith((' ', '.'))
                            or any(ord(char) < 32 or char in '<>:"|?*' for char in leaf)):
                        result['errors'].append(f'不安全或未知的文件路径: {name}')
                        continue
                    allowed = (
                        re.fullmatch(r'notes/note_\d+\.json', name)
                        or re.fullmatch(r'trash/note_\d+_[0-9a-f]{32}\.json', name)
                        or (re.fullmatch(r'(?:notes|trash)/images/[A-Za-z0-9_.-]+', name)
                            and name.rsplit('/', 1)[-1] not in ('.', '..'))
                        or re.fullmatch(r'notes/attachments/note_\d+/[0-9a-f]{32}_[^/\\]+', name)
                        or re.fullmatch(r'notes/conflicts/note_[1-9]\d*\.conflict_remote_\d{8}_\d{6}_\d{6}\.json', name)
                        or re.fullmatch(r'trash/attachments/note_\d+_[0-9a-f]{32}/[0-9a-f]{32}_[^/\\]+', name)
                        or (re.fullmatch(r'styles/[^/\\]+\.css', name)
                            and not any(ord(char) < 32 or char in '<>:"|?*'
                                        for char in name.rsplit('/', 1)[-1]))
                        or name == 'history/key.json'
                        or re.fullmatch(r'history/[0-9a-f]{32}/\d{8}T\d{6}_\d{6}_[0-9a-f]{12}\.snap', name)
                        or name in ('settings.json', 'manifest.json')
                    )
                    if not allowed:
                        result['errors'].append(f'不安全或未知的文件路径: {name}')
                if result['errors']:
                    return result
                for folder in ('notes', 'trash'):
                    if any(name.startswith(folder + '/images/') for name in names) and not any(
                        re.fullmatch(
                            r'note_\d+\.json' if folder == 'notes'
                            else r'note_\d+_[0-9a-f]{32}\.json',
                            name.split('/', 1)[1]
                        )
                        for name in names if name.startswith(folder + '/')
                    ):
                        result['errors'].append(f'{folder} 图片缺少关联便签')
                for name in names:
                    match = re.fullmatch(
                        r'(notes|trash)/attachments/(note_\d+(?:_[0-9a-f]{32})?)/[0-9a-f]{32}_[^/\\]+',
                        name
                    )
                    if match and f'{match.group(1)}/{match.group(2)}.json' not in names:
                        result['errors'].append(f'附件缺少关联便签: {name}')
                if result['errors']:
                    return result
                corrupt = archive.testzip()
                if corrupt:
                    result['errors'].append(f'ZIP 校验失败: {corrupt}')
                    return result
                if 'manifest.json' in names:
                    manifest = json.loads(archive.read('manifest.json'))
                    if not isinstance(manifest, dict):
                        result['errors'].append('SHA256 清单格式无效')
                        return result
                    expected = manifest.get('files', {})
                    if not isinstance(expected, dict) or set(expected) != set(names) - {'manifest.json'}:
                        result['errors'].append('SHA256 清单与文件列表不一致')
                    else:
                        for name, digest in expected.items():
                            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                                result['errors'].append(f'SHA256 不匹配: {name}')
                    result['created_at'] = manifest.get('created_at', '')
                    result['verification'] = 'CRC + SHA256'
                if result['errors']:
                    return result
                for name in names:
                    if re.fullmatch(r'(?:notes|trash)/note_\d+(?:_[0-9a-f]{32})?\.json', name) or name == 'settings.json':
                        data = json.loads(archive.read(name))
                        if not isinstance(data, dict):
                            result['errors'].append(f'JSON 格式错误: {name}')
                            continue
                        if name.startswith('notes/'):
                            result['note_count'] += 1
                            if len(result['titles']) < 5:
                                result['titles'].append(str(data.get('title', '未命名便签')))
                        elif name.startswith('trash/'):
                            result['trash_count'] += 1
                        if name.startswith(('notes/', 'trash/')):
                            if name.startswith('notes/'):
                                background = data.get('background_image', '')
                                if isinstance(background, str) and background.startswith('images/background_'):
                                    if f'notes/{background}' not in names:
                                        result['errors'].append(f'背景图片缺失: {background}')
                            else:
                                background = data.get('trash_background', '')
                                if background and f'trash/images/{background}' not in names:
                                    result['errors'].append(f'回收站背景图片缺失: {background}')
                            for attachment in data.get('attachments', []):
                                relative = attachment.get('path', '') if isinstance(attachment, dict) else ''
                                if not re.fullmatch(r'attachments/note_\d+/[0-9a-f]{32}_[^/\\]+', relative):
                                    result['errors'].append(f'附件路径无效: {name}')
                                    continue
                                if name.startswith('notes/'):
                                    member = f'notes/{relative}'
                                else:
                                    folder = data.get('trash_attachments', '')
                                    member = f'trash/attachments/{folder}/{relative.rsplit("/", 1)[-1]}'
                                if member not in names:
                                    result['errors'].append(f'附件缺失: {member}')
                    elif name.startswith('styles/'):
                        result['style_count'] += 1
                    if '/attachments/' in name:
                        result['attachment_count'] += 1
                        result['attachment_bytes'] += archive.getinfo(name).file_size
                    if name == 'history/key.json':
                        key_data = json.loads(archive.read(name))
                        if not isinstance(key_data, dict) or key_data.get('format') != 1:
                            result['errors'].append('历史密钥元数据无效')
                    if name.startswith('history/') and name.endswith('.snap'):
                        prefix = archive.read(name)[:1]
                        if prefix not in (b'P', b'E'):
                            result['errors'].append(f'历史记录格式无效: {name}')
                if not result['errors']:
                    archived_notes = {
                        name for name in names if re.fullmatch(r'notes/note_\d+\.json', name)
                    }
                    current_notes = set()
                    if os.path.isdir(self.manager.notes_dir):
                        current_notes = {
                            f'notes/{name}' for name in os.listdir(self.manager.notes_dir)
                            if re.fullmatch(r'note_\d+\.json', name)
                        }
                    for name in archived_notes:
                        current = os.path.join(self.manager.notes_dir, name.split('/', 1)[1])
                        if not os.path.isfile(current):
                            result['new_count'] += 1
                        else:
                            with open(current, 'rb') as stream:
                                same = hashlib.sha256(stream.read()).digest() == hashlib.sha256(
                                    archive.read(name)
                                ).digest()
                            result['skipped_count' if same else 'overwrite_count'] += 1
                    if archived_notes:
                        result['removed_count'] = len(current_notes - archived_notes)
                if not result['created_at']:
                    result['created_at'] = datetime.fromtimestamp(
                        os.path.getmtime(backup_path)
                    ).strftime('%Y-%m-%d %H:%M:%S')
                if not names or names == ['manifest.json']:
                    result['errors'].append('备份不包含可恢复数据')
                result['valid'] = not result['errors']
        except (OSError, zipfile.BadZipFile, ValueError, TypeError, KeyError) as exc:
            result['errors'].append(str(exc))
        return result

    def restore_backup_internal(self, backup_path, progress_callback=None):
        """校验、预备份、分阶段替换；异常时恢复原文件。"""
        self.last_safety_backup_path = None
        preview = self.preview_backup(backup_path)
        if not preview['valid']:
            raise ValueError('备份校验失败: ' + '; '.join(preview['errors']))
        safety_name = f'pre_restore_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}'
        safety_path = self.create_backup_internal(safety_name)
        if not safety_path or not self.preview_backup(safety_path)['valid']:
            raise RuntimeError('恢复前安全备份失败，未修改当前数据')
        self.last_safety_backup_path = safety_path
        if progress_callback:
            progress_callback.emit(20)
        with tempfile.TemporaryDirectory(prefix='restore_', dir=self.backup_dir) as temporary:
            stage = os.path.join(temporary, 'stage')
            rollback = os.path.join(temporary, 'rollback')
            os.makedirs(stage)
            os.makedirs(rollback)
            with zipfile.ZipFile(backup_path) as archive:
                names = [
                    item.filename for item in archive.infolist()
                    if not item.is_dir() and item.filename != 'manifest.json'
                ]
                for name in names:
                    path = os.path.join(stage, *name.split('/'))
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, 'wb') as stream:
                        stream.write(archive.read(name))
            if progress_callback:
                progress_callback.emit(50)
            changed_dirs = []
            changed_files = []
            targets = [
                ('notes', self.manager.notes_dir),
                ('trash', os.path.join(get_user_data_dir(), 'trash')),
                ('history', os.path.join(get_user_data_dir(), 'history')),
            ]
            try:
                for folder, target in targets:
                    if not any(name.startswith(folder + '/') for name in names):
                        continue
                    prior = os.path.join(rollback, folder)
                    existed = os.path.exists(target)
                    if existed:
                        os.replace(target, prior)
                    changed_dirs.append((target, prior, existed))
                    os.replace(os.path.join(stage, folder), target)
                file_targets = []
                if 'settings.json' in names:
                    file_targets.append(('settings.json', self.manager.settings_file))
                file_targets += [
                    (name, os.path.join(get_styles_dir(), name.split('/', 1)[1]))
                    for name in names if name.startswith('styles/')
                ]
                for name, target in file_targets:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    prior = os.path.join(rollback, *name.split('/'))
                    existed = os.path.exists(target)
                    if existed:
                        os.makedirs(os.path.dirname(prior), exist_ok=True)
                        os.replace(target, prior)
                    changed_files.append((target, prior, existed))
                    os.replace(os.path.join(stage, *name.split('/')), target)
                if progress_callback:
                    progress_callback.emit(100)
                return True
            except Exception:
                logger.exception('恢复失败，正在回滚当前数据')
                for target, prior, existed in reversed(changed_files):
                    if os.path.exists(target):
                        os.remove(target)
                    if existed:
                        os.replace(prior, target)
                for target, prior, existed in reversed(changed_dirs):
                    if os.path.isdir(target):
                        shutil.rmtree(target)
                    if existed:
                        os.replace(prior, target)
                raise
    
    def _get_notes_state_hash(self):
        """
        计算当前所有便签数据的状态哈希
        
        通过读取 notes 目录下所有 .json 文件的内容和文件名，
        生成一个整体哈希值，用于检测数据是否有变化。
        
        Returns:
            str: SHA256 哈希字符串
        """
        hasher = hashlib.sha256()
        notes_dir = getattr(self.manager, 'notes_dir', '')
        if not notes_dir or not os.path.exists(notes_dir):
            return ''

        try:
            roots = [notes_dir, os.path.join(get_user_data_dir(), 'trash')]
            for root in roots:
                if not os.path.isdir(root):
                    continue
                for current, dirs, files in os.walk(root):
                    dirs.sort()
                    for name in sorted(files):
                        if name.endswith('.tmp'):
                            continue
                        path = os.path.join(current, name)
                        stat = os.stat(path)
                        relative = os.path.relpath(path, root).replace(os.sep, '/')
                        hasher.update(f'{os.path.basename(root)}/{relative}:{stat.st_mtime_ns}:{stat.st_size}'.encode('utf-8'))
            settings_file = getattr(self.manager, 'settings_file', '')
            if settings_file and os.path.isfile(settings_file):
                stat = os.stat(settings_file)
                hasher.update(f'settings:{stat.st_mtime_ns}:{stat.st_size}'.encode('utf-8'))
            for name in sorted(os.listdir(get_styles_dir())):
                if name.endswith('.css'):
                    stat = os.stat(os.path.join(get_styles_dir(), name))
                    hasher.update(f'styles/{name}:{stat.st_mtime_ns}:{stat.st_size}'.encode('utf-8'))
            return hasher.hexdigest()
        except Exception as e:
            logger.debug(f'计算便签状态哈希失败: {e}')
            return ''
    
    def auto_backup(self):
        """
        自动备份
        
        每次定时触发时先检测数据是否有变化，
        若与上次备份状态一致则跳过，避免产生大量重复备份文件。
        """
        if not self.auto_backup_enabled:
            return
        
        # 检测数据是否有变化
        try:
            self.flush_open_notes()
        except Exception as exc:
            logger.warning('自动备份跳过：便签保存失败：%s', exc)
            return
        current_hash = self._get_notes_state_hash()
        if current_hash and current_hash == self._last_backup_hash:
            logger.info('本次检查无修改，跳过本次备份')
            return
        
        # 创建新备份
        try:
            backup_path = self.create_backup()
        except Exception as exc:
            logger.warning('自动备份失败：%s', exc)
            return
        if backup_path:
            self._last_backup_hash = current_hash
            self.cleanup_old_backups()
            logger.info(f'自动备份已创建: {backup_path}')
    
    def cleanup_old_backups(self):
        """
        清理旧的备份文件
        """
        try:
            backup_files = []
            for filename in os.listdir(self.backup_dir):
                if filename.startswith('stickynote_backup_') and filename.endswith('.zip'):
                    file_path = os.path.join(self.backup_dir, filename)
                    backup_files.append((file_path, os.path.getmtime(file_path)))
            
            # 按修改时间排序
            backup_files.sort(key=lambda x: x[1], reverse=True)
            
            # 删除多余的备份
            for file_path, _ in backup_files[self.max_backup_count:]:
                os.remove(file_path)
                print(f"已删除旧备份: {os.path.basename(file_path)}")
        
        except Exception as e:
            print(f"清理备份文件时出错: {e}")
    
    def get_backup_list(self):
        """
        获取备份文件列表
        
        Returns:
            list: 备份文件信息列表
        """
        backup_files = []
        
        try:
            for filename in os.listdir(self.backup_dir):
                if filename.endswith('.zip'):
                    file_path = os.path.join(self.backup_dir, filename)
                    stat = os.stat(file_path)
                    
                    backup_info = {
                        'filename': filename,
                        'path': file_path,
                        'size': self.format_file_size(stat.st_size),
                        'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'timestamp': stat.st_mtime
                    }
                    backup_files.append(backup_info)
            
            # 按时间排序（最新的在前）
            backup_files.sort(key=lambda x: x['timestamp'], reverse=True)
        
        except Exception as e:
            print(f"获取备份列表时出错: {e}")
        
        return backup_files
    
    def format_file_size(self, size_bytes):
        """
        格式化文件大小
        
        Args:
            size_bytes: 文件大小（字节）
            
        Returns:
            str: 格式化的文件大小
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
    
    def set_auto_backup_enabled(self, enabled):
        """
        设置自动备份启用状态
        
        Args:
            enabled: 是否启用
        """
        self.auto_backup_enabled = enabled
        
        if enabled:
            self.auto_backup_timer.start(self.auto_backup_interval * 1000)
        else:
            self.auto_backup_timer.stop()
        
        self.save_backup_settings()
    
    def set_auto_backup_interval(self, interval_seconds):
        """
        设置自动备份间隔
        
        Args:
            interval_seconds: 间隔时间（秒）
        """
        self.auto_backup_interval = interval_seconds
        
        if self.auto_backup_enabled:
            self.auto_backup_timer.stop()
            self.auto_backup_timer.start(interval_seconds * 1000)
        
        self.save_backup_settings()
    
    def set_max_backup_count(self, count):
        """
        设置最大备份数量
        
        Args:
            count: 最大备份数量
        """
        self.max_backup_count = count
        self.save_backup_settings()
    
    def load_backup_settings(self):
        """
        加载备份设置
        """
        settings_file = os.path.join(self.backup_dir, 'backup_settings.json')
        
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                self.auto_backup_enabled = settings.get('auto_backup_enabled', True)
                self.auto_backup_interval = settings.get('auto_backup_interval', 3600)
                self.max_backup_count = settings.get('max_backup_count', 10)
            
            except Exception as e:
                print(f"加载备份设置时出错: {e}")
    
    def save_backup_settings(self):
        """
        保存备份设置
        """
        settings_file = os.path.join(self.backup_dir, 'backup_settings.json')
        
        settings = {
            'auto_backup_enabled': self.auto_backup_enabled,
            'auto_backup_interval': self.auto_backup_interval,
            'max_backup_count': self.max_backup_count
        }
        
        try:
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存备份设置时出错: {e}")
    
    def show_backup_dialog(self, parent=None):
        """
        显示备份管理对话框
        
        Args:
            parent: 父窗口
        """
        dialog = BackupDialog(self, parent)
        dialog.exec_()

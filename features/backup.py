# -*- coding: utf-8 -*-
"""
数据备份功能模块

提供自动和手动备份功能，确保用户数据安全
"""

import os
import json
import shutil
import zipfile
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QFileDialog, QCheckBox, QSpinBox, QGroupBox, QFormLayout
)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont


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
            self.restore_failed.emit(str(e))


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
                # 复制文件到备份目录
                backup_name = os.path.basename(file_path)
                if not backup_name.startswith('stickynote_backup_'):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_name = f"stickynote_backup_imported_{timestamp}.zip"
                
                dest_path = os.path.join(self.backup_manager.backup_dir, backup_name)
                shutil.copy2(file_path, dest_path)
                
                self.refresh_backup_list()
                QMessageBox.information(self, '导入成功', f'备份文件已成功导入:\n{backup_name}')
                
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
        backup_name = item.text().split(' - ')[0]
        backup_path = os.path.join(self.backup_manager.backup_dir, backup_name)
        
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
        
        reply = QMessageBox.question(
            self, '确认恢复', 
            '恢复备份将覆盖当前所有数据，是否继续？\n\n建议在恢复前先创建当前数据的备份。',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            item = selected_items[0]
            backup_name = item.text().split(' - ')[0]
            backup_path = os.path.join(self.backup_manager.backup_dir, backup_name)
            
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
            backup_name = item.text().split(' - ')[0]
            backup_path = os.path.join(self.backup_manager.backup_dir, backup_name)
            
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
    
    def refresh_backup_list(self):
        """
        刷新备份列表
        """
        self.backup_list.clear()
        
        backup_files = self.backup_manager.get_backup_list()
        
        for backup_info in backup_files:
            item_text = f"{backup_info['filename']} - {backup_info['date']} ({backup_info['size']})"
            item = QListWidgetItem(item_text)
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
        self.backup_dir = os.path.join(os.getcwd(), 'backups')
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # 备份设置
        self.auto_backup_enabled = True
        self.auto_backup_interval = 3600  # 1小时
        self.max_backup_count = 10
        
        # 自动备份定时器
        self.auto_backup_timer = QTimer()
        self.auto_backup_timer.timeout.connect(self.auto_backup)
        
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
        return self.create_backup_internal(backup_name)
    
    def create_backup_internal(self, backup_name=None, progress_callback=None):
        """
        创建备份（内部实现）
        
        Args:
            backup_name: 备份名称
            progress_callback: 进度回调函数
            
        Returns:
            str: 备份文件路径，失败返回None
        """
        if backup_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"stickynote_backup_{timestamp}"
        
        backup_path = os.path.join(self.backup_dir, f"{backup_name}.zip")
        
        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                total_files = 0
                processed_files = 0
                
                # 计算总文件数
                notes_dir = self.manager.notes_dir
                if os.path.exists(notes_dir):
                    for filename in os.listdir(notes_dir):
                        if filename.endswith('.json'):
                            total_files += 1
                
                settings_file = self.manager.settings_file
                if os.path.exists(settings_file):
                    total_files += 1
                
                styles_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'styles')
                if os.path.exists(styles_dir):
                    for filename in os.listdir(styles_dir):
                        if filename.endswith('.css'):
                            total_files += 1
                
                # 备份便签数据
                if os.path.exists(notes_dir):
                    for filename in os.listdir(notes_dir):
                        if filename.endswith('.json'):
                            file_path = os.path.join(notes_dir, filename)
                            zipf.write(file_path, f"notes/{filename}")
                            processed_files += 1
                            if progress_callback:
                                progress = int((processed_files / total_files) * 100)
                                progress_callback.emit(progress)
                
                # 备份设置文件
                if os.path.exists(settings_file):
                    zipf.write(settings_file, "settings.json")
                    processed_files += 1
                    if progress_callback:
                        progress = int((processed_files / total_files) * 100)
                        progress_callback.emit(progress)
                
                # 备份主题文件
                if os.path.exists(styles_dir):
                    for filename in os.listdir(styles_dir):
                        if filename.endswith('.css'):
                            file_path = os.path.join(styles_dir, filename)
                            zipf.write(file_path, f"styles/{filename}")
                            processed_files += 1
                            if progress_callback:
                                progress = int((processed_files / total_files) * 100)
                                progress_callback.emit(progress)
                
                if progress_callback:
                    progress_callback.emit(100)
            
            return backup_path
        
        except Exception as e:
            print(f'创建备份时出错: {e}')
            return None
    
    def restore_backup_internal(self, backup_path, progress_callback=None):
        """
        恢复备份（内部实现）
        
        Args:
            backup_path: 备份文件路径
            progress_callback: 进度回调函数
            
        Returns:
            bool: 恢复是否成功
        """
        try:
            # 创建临时目录
            temp_dir = os.path.join(self.backup_dir, 'temp_restore')
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir)
            
            # 解压备份文件
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(temp_dir)
            
            if progress_callback:
                progress_callback.emit(30)
            
            # 恢复便签数据
            temp_notes_dir = os.path.join(temp_dir, 'notes')
            if os.path.exists(temp_notes_dir):
                if os.path.exists(self.manager.notes_dir):
                    shutil.rmtree(self.manager.notes_dir)
                shutil.copytree(temp_notes_dir, self.manager.notes_dir)
            
            if progress_callback:
                progress_callback.emit(60)
            
            # 恢复设置文件
            temp_settings = os.path.join(temp_dir, 'settings.json')
            if os.path.exists(temp_settings):
                shutil.copy2(temp_settings, self.manager.settings_file)
            
            if progress_callback:
                progress_callback.emit(80)
            
            # 恢复主题文件
            temp_styles_dir = os.path.join(temp_dir, 'styles')
            styles_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'styles')
            if os.path.exists(temp_styles_dir):
                if not os.path.exists(styles_dir):
                    os.makedirs(styles_dir)
                for filename in os.listdir(temp_styles_dir):
                    if filename.endswith('.css'):
                        src_path = os.path.join(temp_styles_dir, filename)
                        dst_path = os.path.join(styles_dir, filename)
                        shutil.copy2(src_path, dst_path)
            
            if progress_callback:
                progress_callback.emit(90)
            
            # 清理临时目录
            shutil.rmtree(temp_dir)
            
            if progress_callback:
                progress_callback.emit(100)
            
            return True
        
        except Exception as e:
            print(f'恢复备份时出错: {e}')
            return False
    
    def auto_backup(self):
        """
        自动备份
        """
        if not self.auto_backup_enabled:
            return
        
        # 清理旧备份
        self.cleanup_old_backups()
        
        # 创建新备份
        backup_path = self.create_backup()
        if backup_path:
            print(f"自动备份已创建: {backup_path}")
    
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
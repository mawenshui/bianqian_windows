# -*- coding: utf-8 -*-
"""
同步设置对话框

提供云同步配置 UI，包括 WebDAV 连接设置和本地同步目录选择。
"""

import logging

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QProgressBar, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt

logger = logging.getLogger(__name__)


class SyncDialog(QDialog):
    """同步设置与状态对话框"""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle('云同步设置')
        self.setMinimumSize(500, 450)
        self.resize(560, 520)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self._bound_sync_engine = None
        self._init_ui()
        self._bind_sync_engine()
        # 应用主题适配
        try:
            from features.theme_helper import apply_dialog_theme, get_current_theme_css
            apply_dialog_theme(self, get_current_theme_css(manager))
        except Exception:
            pass

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 启用开关
        self.enabled_checkbox = QCheckBox('启用云同步')
        sync_enabled = self.manager.config.get('sync.enabled', False)
        self.enabled_checkbox.setChecked(sync_enabled)
        self.enabled_checkbox.stateChanged.connect(self._on_enabled_changed)
        layout.addWidget(self.enabled_checkbox)

        # 同步方式
        provider_group = QGroupBox('同步方式')
        provider_layout = QFormLayout()

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(['WebDAV (坚果云/Nextcloud)', '本地文件夹'])
        current_provider = self.manager.config.get('sync.provider', 'webdav')
        if current_provider == 'local':
            self.provider_combo.setCurrentIndex(1)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        provider_layout.addRow('同步协议:', self.provider_combo)

        provider_group.setLayout(provider_layout)
        layout.addWidget(provider_group)

        # WebDAV 设置
        self.webdav_group = QGroupBox('WebDAV 设置')
        webdav_layout = QFormLayout()

        self.webdav_url = QLineEdit()
        self.webdav_url.setPlaceholderText('https://dav.jianguoyun.com/dav/')
        self.webdav_url.setText(self.manager.config.get('sync.webdav.url', ''))
        self.webdav_url.setAccessibleName('WebDAV 服务器地址')
        webdav_layout.addRow('服务器地址:', self.webdav_url)

        self.webdav_username = QLineEdit()
        self.webdav_username.setText(self.manager.config.get('sync.webdav.username', ''))
        self.webdav_username.setAccessibleName('WebDAV 用户名')
        webdav_layout.addRow('用户名:', self.webdav_username)

        self.webdav_password = QLineEdit()
        self.webdav_password.setEchoMode(QLineEdit.Password)
        self.webdav_password.setAccessibleName('WebDAV 密码')
        protected_password = (
            self.manager.config.get('sync.webdav.password_encrypted', '')
            or self.manager.config.get('sync.webdav.password', '')
        )
        if protected_password:
            try:
                from features.secret_storage import reveal_secret
                self.webdav_password.setText(reveal_secret(protected_password))
            except Exception:
                self.webdav_password.setPlaceholderText('凭据不可读取，请重新输入')
        webdav_layout.addRow('密码:', self.webdav_password)

        self.webdav_path = QLineEdit()
        self.webdav_path.setPlaceholderText('/StickyNote/')
        self.webdav_path.setText(self.manager.config.get('sync.webdav.remote_path', '/StickyNote/'))
        self.webdav_path.setAccessibleName('WebDAV 远端路径')
        webdav_layout.addRow('远端路径:', self.webdav_path)

        test_btn = QPushButton('测试连接')
        test_btn.clicked.connect(self._on_test_connection)
        webdav_layout.addRow('', test_btn)

        self.webdav_group.setLayout(webdav_layout)
        layout.addWidget(self.webdav_group)

        # 本地文件夹设置
        self.local_group = QGroupBox('本地同步目录')
        local_layout = QHBoxLayout()

        self.local_dir_input = QLineEdit()
        self.local_dir_input.setPlaceholderText('选择本地同步文件夹...')
        self.local_dir_input.setText(
            self.manager.config.get('sync.local_folder', '')
            or self.manager.config.get('sync.local.sync_dir', '')
        )
        self.local_dir_input.setAccessibleName('本地同步目录')
        local_layout.addWidget(self.local_dir_input)

        browse_btn = QPushButton('浏览...')
        browse_btn.clicked.connect(self._on_browse_dir)
        local_layout.addWidget(browse_btn)

        self.local_group.setLayout(local_layout)
        layout.addWidget(self.local_group)

        # 同步选项
        options_group = QGroupBox('同步选项')
        options_layout = QVBoxLayout()

        self.auto_sync_checkbox = QCheckBox('自动同步')
        self.auto_sync_checkbox.setChecked(self.manager.config.get('sync.auto_sync', True))
        options_layout.addWidget(self.auto_sync_checkbox)

        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel('同步间隔:'))
        from PyQt5.QtWidgets import QSpinBox
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(1, 60)
        self.interval_spinbox.setSuffix(' 分钟')
        self.interval_spinbox.setValue(self.manager.config.get('sync.sync_interval_minutes', 5))
        interval_layout.addWidget(self.interval_spinbox)
        interval_layout.addStretch()
        options_layout.addLayout(interval_layout)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # 同步状态
        status_layout = QHBoxLayout()
        self.sync_btn = QPushButton('立即同步')
        self.sync_btn.setAccessibleName('立即执行云同步')
        self.sync_btn.clicked.connect(self._on_sync_now)
        status_layout.addWidget(self.sync_btn)

        self.status_label = QLabel('')
        self.status_label.setAccessibleName('云同步状态')
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        layout.addLayout(status_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # 保存按钮
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        save_btn = QPushButton('保存设置')
        save_btn.clicked.connect(self._on_save)
        save_layout.addWidget(save_btn)
        layout.addLayout(save_layout)

        self.setLayout(layout)
        self._on_provider_changed()

    def _on_enabled_changed(self, state):
        enabled = bool(state)
        self.webdav_group.setEnabled(enabled and self.provider_combo.currentIndex() == 0)
        self.local_group.setEnabled(enabled and self.provider_combo.currentIndex() == 1)

    def _on_provider_changed(self):
        is_webdav = self.provider_combo.currentIndex() == 0
        enabled = self.enabled_checkbox.isChecked()
        self.webdav_group.setVisible(is_webdav)
        self.webdav_group.setEnabled(enabled)
        self.local_group.setVisible(not is_webdav)
        self.local_group.setEnabled(enabled)

    def _on_test_connection(self):
        from features.sync.webdav_client import WebDAVClient
        url = self.webdav_url.text()
        username = self.webdav_username.text()
        password = self.webdav_password.text()
        remote_path = self.webdav_path.text() or '/StickyNote/'

        if not all([url, username, password]):
            QMessageBox.warning(self, '提示', '请填写完整的 WebDAV 连接信息')
            return

        client = WebDAVClient(url, username, password, remote_path)
        if client.check_connection():
            QMessageBox.information(self, '连接成功', 'WebDAV 连接测试成功！')
        else:
            QMessageBox.warning(self, '连接失败', '无法连接到 WebDAV 服务器，请检查设置。')

    def _on_browse_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, '选择同步目录')
        if dir_path:
            self.local_dir_input.setText(dir_path)

    def _on_sync_now(self):
        if hasattr(self.manager, 'sync_engine') and self.manager.sync_engine:
            self.sync_btn.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.status_label.setText('正在同步...')
            self.manager.sync_engine.sync_now()
        else:
            QMessageBox.warning(self, '提示', '同步引擎未初始化，请先保存设置。')

    def _bind_sync_engine(self):
        """Bind status feedback to the manager's current engine exactly once."""
        engine = getattr(self.manager, 'sync_engine', None)
        if engine is self._bound_sync_engine:
            return
        previous = self._bound_sync_engine
        if previous is not None:
            for signal, slot in (
                (previous.sync_started, self._on_sync_started),
                (previous.sync_progress, self._on_sync_progress),
                (previous.sync_completed, self._on_sync_completed),
                (previous.sync_error, self._on_sync_error),
            ):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
        self._bound_sync_engine = engine
        if engine is not None:
            engine.sync_started.connect(self._on_sync_started)
            engine.sync_progress.connect(self._on_sync_progress)
            engine.sync_completed.connect(self._on_sync_completed)
            engine.sync_error.connect(self._on_sync_error)

    def _on_sync_started(self):
        self.sync_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText('正在同步...')

    def _on_sync_progress(self, current, total, filename):
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        self.status_label.setText(f'正在同步 {filename}（{current}/{total}）')

    def _on_sync_completed(self, summary):
        self.sync_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(
            '同步完成：上传 {uploaded}，下载 {downloaded}，冲突 {conflicts}，错误 {errors}'.format(
                uploaded=summary.get('uploaded', 0),
                downloaded=summary.get('downloaded', 0),
                conflicts=summary.get('conflicts', 0),
                errors=summary.get('errors', 0),
            )
        )

    def _on_sync_error(self, message):
        self.sync_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f'同步失败：{message}')

    def _on_save(self):
        from features.secret_storage import protect_secret
        self.manager.config.set('sync.enabled', self.enabled_checkbox.isChecked(), auto_save=False)
        provider = 'webdav' if self.provider_combo.currentIndex() == 0 else 'local'
        self.manager.config.set('sync.provider', provider, auto_save=False)
        self.manager.config.set('sync.webdav.url', self.webdav_url.text(), auto_save=False)
        self.manager.config.set('sync.webdav.username', self.webdav_username.text(), auto_save=False)
        try:
            protected_password = protect_secret(self.webdav_password.text())
        except Exception as exc:
            QMessageBox.warning(self, '保存失败', f'无法安全保存 WebDAV 密码：{exc}')
            return
        self.manager.config.set(
            'sync.webdav.password_encrypted', protected_password, auto_save=False
        )
        self.manager.config.set('sync.webdav.password', '', auto_save=False)
        self.manager.config.set('sync.webdav.remote_path', self.webdav_path.text(), auto_save=False)
        self.manager.config.set('sync.local_folder', self.local_dir_input.text(), auto_save=False)
        self.manager.config.set('sync.local.sync_dir', '', auto_save=False)
        self.manager.config.set('sync.auto_sync', self.auto_sync_checkbox.isChecked(), auto_save=False)
        self.manager.config.set('sync.sync_interval_minutes', self.interval_spinbox.value(), auto_save=False)
        self.manager.config.save()

        # 初始化同步引擎
        if hasattr(self.manager, 'setup_sync_engine'):
            self.manager.setup_sync_engine()
            self._bind_sync_engine()

        QMessageBox.information(self, '保存成功', '同步设置已保存。')

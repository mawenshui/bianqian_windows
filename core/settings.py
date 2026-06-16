# -*- coding: utf-8 -*-
"""
设置对话框模块

提供主题选择和字体设置界面，使用标签页组织。
"""

import os
from typing import Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QTabWidget, QLabel, QComboBox, QCheckBox,
    QPushButton, QSpinBox, QLineEdit, QTextEdit, QFrame,
    QFontComboBox, QWidget, QProgressBar, QMessageBox, QListWidget,
    QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, QObject
from PyQt5.QtGui import QFont, QKeySequence

from core import get_styles_dir, __version__


class SettingsDialog(QDialog):
    """
    应用设置对话框（非模态）

    包含两个标签页：
    - 主题设置：选择默认主题并预览效果
    - 字体设置：选择默认字体家族、大小和样式
    """

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        # 必须在 setWindowModality 之前设置窗口标志（setWindowFlags 会重建原生句柄）
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint
        )
        self.setWindowModality(Qt.NonModal)
        self.initUI()
        # 应用主题适配
        try:
            from features.theme_helper import apply_dialog_theme, get_current_theme_css
            apply_dialog_theme(self, get_current_theme_css(manager))
        except Exception:
            pass

    def initUI(self):
        self.setWindowTitle('\u8bbe\u7f6e')
        self.setFixedSize(600, 500)

        tab_widget = QTabWidget()

        theme_tab = QWidget()
        self.setup_theme_tab(theme_tab)
        tab_widget.addTab(theme_tab, "\u4e3b\u9898\u8bbe\u7f6e")

        font_tab = QWidget()
        self.setup_font_tab(font_tab)
        tab_widget.addTab(font_tab, "\u5b57\u4f53\u8bbe\u7f6e")

        update_tab = QWidget()
        self.setup_update_tab(update_tab)
        tab_widget.addTab(update_tab, "\u66f4\u65b0\u8bbe\u7f6e")

        security_tab = QWidget()
        self.setup_security_tab(security_tab)
        tab_widget.addTab(security_tab, "安全设置")

        sync_tab = QWidget()
        self.setup_sync_tab(sync_tab)
        tab_widget.addTab(sync_tab, "云同步")

        plugins_tab = QWidget()
        self.setup_plugins_tab(plugins_tab)
        tab_widget.addTab(plugins_tab, "插件")

        shortcuts_tab = QWidget()
        self.setup_shortcuts_tab(shortcuts_tab)
        tab_widget.addTab(shortcuts_tab, "快捷键")

        main_layout = QVBoxLayout()
        main_layout.addWidget(tab_widget)

        author_label = QLabel(f"v{__version__} | By MaWenshui")
        author_label.setAlignment(Qt.AlignCenter)
        author_label.setStyleSheet("color: gray; font-size: 10pt;")
        main_layout.addWidget(author_label)

        self.setLayout(main_layout)

    def setup_theme_tab(self, tab_widget):
        layout = QVBoxLayout()

        # 主题选择区域
        theme_group = QGroupBox("\u4e3b\u9898\u9009\u62e9")
        theme_layout = QFormLayout()

        self.theme_label = QLabel("\u9009\u62e9\u4fbf\u7b7e\u9ed8\u8ba4\u4e3b\u9898:")
        self.theme_combo = QComboBox()
        self.load_themes()

        current_theme_css = self.manager.get_default_theme_css()
        current_theme_name = self.manager.get_theme_name_by_css(current_theme_css)
        if current_theme_name:
            index = self.theme_combo.findText(current_theme_name)
            if index != -1:
                self.theme_combo.setCurrentIndex(index)
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)

        theme_layout.addRow(self.theme_label, self.theme_combo)
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)

        # 主题预览区域
        preview_group = QGroupBox("\u4e3b\u9898\u9884\u89c8")
        preview_layout = QVBoxLayout()

        self.preview_note = QFrame()
        self.preview_note.setFixedSize(280, 200)
        self.preview_note.setFrameStyle(QFrame.StyledPanel)

        preview_note_layout = QVBoxLayout()
        self.preview_title = QLineEdit("\u9884\u89c8\u6807\u9898")
        self.preview_title.setReadOnly(True)
        preview_note_layout.addWidget(self.preview_title)

        self.preview_content = QTextEdit()
        self.preview_content.setPlainText("\u8fd9\u662f\u4e3b\u9898\u9884\u89c8\u5185\u5bb9\n\u53ef\u4ee5\u770b\u5230\u5f53\u524d\u4e3b\u9898\u7684\u6837\u5f0f\u6548\u679c")
        self.preview_content.setReadOnly(True)
        preview_note_layout.addWidget(self.preview_content)

        self.preview_note.setLayout(preview_note_layout)
        preview_layout.addWidget(self.preview_note)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        self.update_theme_preview()
        tab_widget.setLayout(layout)

    def setup_font_tab(self, tab_widget):
        layout = QVBoxLayout()

        font_group = QGroupBox("\u5b57\u4f53\u8bbe\u7f6e")
        font_layout = QFormLayout()

        self.font_family_combo = QFontComboBox()
        current_font = self.manager.get_default_font()
        if current_font:
            self.font_family_combo.setCurrentFont(QFont(current_font['family']))
        self.font_family_combo.currentFontChanged.connect(self.on_font_changed)
        font_layout.addRow("\u5b57\u4f53\u65cf:", self.font_family_combo)

        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setRange(8, 72)
        self.font_size_spinbox.setValue(current_font.get('size', 12) if current_font else 12)
        self.font_size_spinbox.setSuffix(' pt')
        self.font_size_spinbox.valueChanged.connect(self.on_font_changed)
        font_layout.addRow("\u5b57\u4f53\u5927\u5c0f:", self.font_size_spinbox)

        font_style_layout = QHBoxLayout()
        self.font_bold_checkbox = QCheckBox("\u7c97\u4f53")
        self.font_italic_checkbox = QCheckBox("\u659c\u4f53")
        if current_font:
            self.font_bold_checkbox.setChecked(current_font.get('bold', False))
            self.font_italic_checkbox.setChecked(current_font.get('italic', False))
        self.font_bold_checkbox.stateChanged.connect(self.on_font_changed)
        self.font_italic_checkbox.stateChanged.connect(self.on_font_changed)
        font_style_layout.addWidget(self.font_bold_checkbox)
        font_style_layout.addWidget(self.font_italic_checkbox)
        font_style_layout.addStretch()
        font_layout.addRow("\u5b57\u4f53\u6837\u5f0f:", font_style_layout)

        font_group.setLayout(font_layout)
        layout.addWidget(font_group)

        # 字体预览
        font_preview_group = QGroupBox("\u5b57\u4f53\u9884\u89c8")
        font_preview_layout = QVBoxLayout()
        self.font_preview_label = QLabel("\u8fd9\u662f\u5b57\u4f53\u9884\u89c8\u6587\u672c\nABCDEFG abcdefg 12345")
        self.font_preview_label.setAlignment(Qt.AlignCenter)
        self.font_preview_label.setStyleSheet("border: 1px solid gray; padding: 20px; background-color: white;")
        self.font_preview_label.setMinimumHeight(100)
        font_preview_layout.addWidget(self.font_preview_label)
        font_preview_group.setLayout(font_preview_layout)
        layout.addWidget(font_preview_group)

        # 重置按钮
        reset_layout = QHBoxLayout()
        reset_layout.addStretch()
        reset_font_btn = QPushButton("\u91cd\u7f6e\u4e3a\u9ed8\u8ba4\u5b57\u4f53")
        reset_font_btn.clicked.connect(self.reset_font_settings)
        reset_layout.addWidget(reset_font_btn)
        layout.addLayout(reset_layout)

        self.update_font_preview()
        tab_widget.setLayout(layout)

    def load_themes(self):
        self.themes = self.manager.get_available_themes()
        self.theme_combo.clear()
        for theme_name in self.themes.keys():
            self.theme_combo.addItem(theme_name)

    def on_theme_changed(self):
        selected_theme_name = self.theme_combo.currentText()
        selected_theme_css = self.themes.get(selected_theme_name, "soft_yellow.css")
        self.manager.set_default_theme(selected_theme_css)
        self.manager.apply_theme_to_all_notes()
        self.update_theme_preview()

    def update_theme_preview(self):
        if not hasattr(self, 'preview_note'):
            return
        selected_theme_name = self.theme_combo.currentText()
        selected_theme_css = self.themes.get(selected_theme_name, "soft_yellow.css")
        css_path = os.path.join(get_styles_dir(), selected_theme_css)
        if os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8') as f:
                css_content = f.read()
            self.preview_title.setStyleSheet(css_content)
            self.preview_content.setStyleSheet(css_content)
            self.preview_note.setStyleSheet(css_content)

    def on_font_changed(self):
        font_settings = {
            'family': self.font_family_combo.currentFont().family(),
            'size': self.font_size_spinbox.value(),
            'bold': self.font_bold_checkbox.isChecked(),
            'italic': self.font_italic_checkbox.isChecked()
        }
        self.manager.set_default_font(font_settings)
        self.update_font_preview()
        self.manager.apply_font_to_all_notes()

    def update_font_preview(self):
        if not hasattr(self, 'font_preview_label'):
            return
        font = QFont()
        font.setFamily(self.font_family_combo.currentFont().family())
        font.setPointSize(self.font_size_spinbox.value())
        font.setBold(self.font_bold_checkbox.isChecked())
        font.setItalic(self.font_italic_checkbox.isChecked())
        self.font_preview_label.setFont(font)

    def reset_font_settings(self):
        self.font_family_combo.setCurrentFont(QFont("\u5fae\u8f6f\u96c5\u9ed1"))
        self.font_size_spinbox.setValue(12)
        self.font_bold_checkbox.setChecked(False)
        self.font_italic_checkbox.setChecked(False)
        self.on_font_changed()

    def change_theme(self):
        self.on_theme_changed()

    # ==================== 更新设置 ====================

    def setup_update_tab(self, tab_widget):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 自动检查更新
        auto_group = QGroupBox("\u81ea\u52a8\u66f4\u65b0")
        auto_layout = QVBoxLayout()

        self.auto_update_checkbox = QCheckBox("\u542f\u52a8\u540e\u81ea\u52a8\u68c0\u67e5\u65b0\u7248\u672c")
        auto_check = self.manager.settings.get('auto_check_update', True)
        self.auto_update_checkbox.setChecked(auto_check)
        self.auto_update_checkbox.stateChanged.connect(self.on_auto_update_changed)
        auto_layout.addWidget(self.auto_update_checkbox)

        hint_label = QLabel("\u542f\u7528\u540e\uff0c\u6bcf\u6b21\u542f\u52a8\u5e94\u7528\u65f6\u4f1a\u5728\u540e\u53f0\u81ea\u52a8\u68c0\u67e5 GitHub \u662f\u5426\u6709\u65b0\u7248\u672c\u53d1\u5e03\u3002")
        hint_label.setStyleSheet("color: #888; font-size: 10pt;")
        hint_label.setWordWrap(True)
        auto_layout.addWidget(hint_label)

        auto_group.setLayout(auto_layout)
        layout.addWidget(auto_group)

        # 手动检查
        manual_group = QGroupBox("\u624b\u52a8\u68c0\u67e5")
        manual_layout = QVBoxLayout()

        manual_hint = QLabel("\u70b9\u51fb\u4e0b\u65b9\u6309\u94ae\u7acb\u5373\u68c0\u67e5\u662f\u5426\u6709\u65b0\u7248\u672c\u53ef\u7528\u3002")
        manual_hint.setWordWrap(True)
        manual_layout.addWidget(manual_hint)

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.check_update_btn = QPushButton("\u7acb\u5373\u68c0\u67e5\u66f4\u65b0")
        self.check_update_btn.setFixedHeight(36)
        self.check_update_btn.clicked.connect(self.on_manual_check_update)
        btn_layout.addWidget(self.check_update_btn)

        self.cancel_check_btn = QPushButton("\u53d6\u6d88\u68c0\u67e5")
        self.cancel_check_btn.setFixedHeight(36)
        self.cancel_check_btn.clicked.connect(self.on_cancel_check_update)
        self.cancel_check_btn.setVisible(False)
        self.cancel_check_btn.setStyleSheet(
            'QPushButton { color: #e74c3c; border: 1px solid #e74c3c; border-radius: 4px; padding: 6px 16px; }'
            'QPushButton:hover { background-color: #fde8e8; }'
        )
        btn_layout.addWidget(self.cancel_check_btn)
        btn_layout.addStretch()

        manual_layout.addLayout(btn_layout)

        # 进度条（检查中显示）
        self.check_progress_bar = QProgressBar()
        self.check_progress_bar.setRange(0, 0)  # 不确定模式（来回滚动）
        self.check_progress_bar.setFixedHeight(8)
        self.check_progress_bar.setTextVisible(False)
        self.check_progress_bar.setVisible(False)
        manual_layout.addWidget(self.check_progress_bar)

        self.update_status_label = QLabel("")
        self.update_status_label.setStyleSheet("color: #4a86e8;")
        self.update_status_label.setWordWrap(True)
        manual_layout.addWidget(self.update_status_label)

        manual_group.setLayout(manual_layout)
        layout.addWidget(manual_group)

        layout.addStretch()
        tab_widget.setLayout(layout)

    def on_auto_update_changed(self):
        enabled = self.auto_update_checkbox.isChecked()
        self.manager.settings['auto_check_update'] = enabled
        self.manager.save_settings()

    def on_manual_check_update(self):
        """手动触发检查更新"""
        # 隐藏上次的行内更新结果
        if hasattr(self, 'inline_update_group'):
            self.inline_update_group.setVisible(False)
        self.check_update_btn.setEnabled(False)
        self.check_update_btn.setText("\u6b63\u5728\u68c0\u67e5...")
        self.cancel_check_btn.setVisible(True)
        self.check_progress_bar.setVisible(True)
        self.update_status_label.setText("\u6b63\u5728\u8fde\u63a5 GitHub...")
        self.update_status_label.setStyleSheet("color: #4a86e8;")
        self.manager.check_for_updates(manual=True, source='settings')

    def on_cancel_check_update(self):
        """取消检查更新"""
        self.update_status_label.setText("\u6b63\u5728\u53d6\u6d88...")
        self.update_status_label.setStyleSheet("color: #e67e22;")
        self.cancel_check_btn.setEnabled(False)
        self.manager.cancel_update_check()

    def on_check_status_update(self, status_text):
        """接收来自 UpdateChecker 的状态更新"""
        self.update_status_label.setText(status_text)

    def show_inline_update_info(self, update_info, current_version):
        """
        在设置页面的更新标签页内行内展示新版本信息（不弹模态对话框）。
        
        包含：版本号对比、更新日志、立即更新/稍后提醒/跳过按钮。
        """
        # 隐藏进度条和取消按钮
        self.check_progress_bar.setVisible(False)
        self.cancel_check_btn.setVisible(False)
        self.check_update_btn.setEnabled(True)
        self.check_update_btn.setText("\u7acb\u5373\u68c0\u67e5\u66f4\u65b0")

        # 确保 inline_update_group 存在
        if not hasattr(self, 'inline_update_group'):
            self._create_inline_update_widgets()

        # 填充内容
        self.inline_version_label.setText(
            f'<h3 style="color:#27ae60;">🎉 发现新版本 v{update_info["version"]}</h3>'
            f'<p>当前版本: <b>v{current_version}</b>  →  最新版本: <b>v{update_info["version"]}</b></p>'
        )
        body = update_info.get('body', '\u65e0\u8be6\u7ec6\u4fe1\u606f')
        self.inline_changelog.setPlainText(body)

        # 保存引用供按钮回调使用
        self._inline_update_info = update_info

        self.inline_update_group.setVisible(True)
        self.update_status_label.setText("")

    def _create_inline_update_widgets(self):
        """创建行内更新信息展示控件（延迟创建，插入到按钮区域之后）"""
        from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout

        self.inline_update_group = QGroupBox("\u65b0\u7248\u672c\u53ef\u7528")
        inline_layout = QVBoxLayout()
        inline_layout.setContentsMargins(12, 12, 12, 12)
        inline_layout.setSpacing(8)

        # 版本信息
        self.inline_version_label = QLabel()
        self.inline_version_label.setTextFormat(Qt.RichText)
        self.inline_version_label.setWordWrap(True)
        inline_layout.addWidget(self.inline_version_label)

        # 更新日志
        self.inline_changelog = QTextEdit()
        self.inline_changelog.setReadOnly(True)
        self.inline_changelog.setMaximumHeight(140)
        inline_layout.addWidget(self.inline_changelog)

        # 操作按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        later_btn = QPushButton("\u7a0d\u540e\u63d0\u9192")
        later_btn.clicked.connect(self._on_inline_later)
        btn_row.addWidget(later_btn)

        skip_btn = QPushButton("\u8df3\u8fc7\u6b64\u7248\u672c")
        skip_btn.setStyleSheet('color: #888;')
        skip_btn.clicked.connect(self._on_inline_skip)
        btn_row.addWidget(skip_btn)

        btn_row.addStretch()

        update_btn = QPushButton("\u7acb\u5373\u66f4\u65b0")
        update_btn.setStyleSheet(
            'QPushButton { padding: 8px 24px; font-weight: bold; '
            'background-color: #4a86e8; color: white; border-radius: 4px; }'
            'QPushButton:hover { background-color: #3a76d8; }'
        )
        update_btn.clicked.connect(self._on_inline_update)
        btn_row.addWidget(update_btn)

        inline_layout.addLayout(btn_row)

        self.inline_update_group.setLayout(inline_layout)
        self.inline_update_group.setVisible(False)

        # 插入到更新标签页布局的末尾（添加到 tab_widget 布局）
        # 找到更新标签页的布局并添加
        parent_tab = self.check_progress_bar.parent()  # 更新标签页的 widget
        if parent_tab:
            layout = parent_tab.layout()
            if layout:
                # 在 stretch 之前插入
                layout.insertWidget(layout.count() - 1, self.inline_update_group)

    def _on_inline_later(self):
        """行内'稍后提醒'按钮"""
        if hasattr(self, '_inline_update_info'):
            self.manager.settings['last_dismissed_version'] = self._inline_update_info['tag']
            self.manager.save_settings()
        self.inline_update_group.setVisible(False)
        self.update_status_label.setText("已设置为稍后提醒")
        self.update_status_label.setStyleSheet("color: #888;")

    def _on_inline_skip(self):
        """行内'跳过此版本'按钮"""
        if hasattr(self, '_inline_update_info'):
            self.manager.settings['skip_version'] = self._inline_update_info['tag']
            self.manager.save_settings()
        self.inline_update_group.setVisible(False)
        self.update_status_label.setText("已跳过此版本")
        self.update_status_label.setStyleSheet("color: #888;")

    def _on_inline_update(self):
        """行内'立即更新'按钮"""
        if hasattr(self, '_inline_update_info'):
            self.manager._start_download_update(self._inline_update_info)

    # ==================== 安全设置 ====================

    def setup_security_tab(self, tab_widget):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 主密码设置
        master_group = QGroupBox("主密码")
        master_layout = QVBoxLayout()

        hint = QLabel("设置主密码后，每次启动应用时需要输入密码。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        master_layout.addWidget(hint)

        self.master_pwd_checkbox = QCheckBox("启用主密码")
        has_master = bool(self.manager.config.get('security.require_master_password', False))
        self.master_pwd_checkbox.setChecked(has_master)
        self.master_pwd_checkbox.stateChanged.connect(self._on_master_pwd_toggled)
        master_layout.addWidget(self.master_pwd_checkbox)

        btn_row = QHBoxLayout()
        self.set_master_pwd_btn = QPushButton("设置/修改主密码")
        self.set_master_pwd_btn.clicked.connect(self._on_set_master_password)
        btn_row.addWidget(self.set_master_pwd_btn)
        btn_row.addStretch()
        master_layout.addLayout(btn_row)

        master_group.setLayout(master_layout)
        layout.addWidget(master_group)

        # 加密说明
        info_label = QLabel("ℹ️ 便签加密使用 AES-256-GCM，密钥通过 PBKDF2 派生（480000 轮）。\n"
                           "密码哈希使用 Argon2id（回退到 PBKDF2）。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 9pt;")
        layout.addWidget(info_label)

        layout.addStretch()
        tab_widget.setLayout(layout)

    def _on_master_pwd_toggled(self):
        enabled = self.master_pwd_checkbox.isChecked()
        if enabled:
            # 启用主密码 — 直接保存配置
            self.manager.config.set('security.require_master_password', True)
        else:
            # 禁用主密码 — 需要先验证当前密码
            master_hash = self.manager.config.get('security.master_password_hash', '')
            master_salt_str = self.manager.config.get('security.master_password_salt', '')
            
            if not master_hash:
                # 未设置密码，直接允许禁用
                self.manager.config.set('security.require_master_password', False)
                return
            
            # 要求用户输入当前主密码
            import base64
            from PyQt5.QtWidgets import QInputDialog, QLineEdit
            password, ok = QInputDialog.getText(
                self, '验证主密码',
                '请输入当前主密码以确认禁用：',
                QLineEdit.Password
            )
            if not ok or not password:
                # 用户取消，恢复勾选状态
                self.master_pwd_checkbox.blockSignals(True)
                self.master_pwd_checkbox.setChecked(True)
                self.master_pwd_checkbox.blockSignals(False)
                return
            
            # 验证密码
            from features.encryption import NoteEncryption
            enc = NoteEncryption()
            master_salt = None
            if master_salt_str:
                try:
                    master_salt = base64.b64decode(master_salt_str)
                except Exception:
                    master_salt = None
            
            try:
                if enc.verify_password(password, master_hash, master_salt):
                    self.manager.config.set('security.require_master_password', False)
                    QMessageBox.information(self, '已禁用', '主密码已禁用。')
                else:
                    QMessageBox.warning(self, '验证失败', '主密码不正确，无法禁用。')
                    self.master_pwd_checkbox.blockSignals(True)
                    self.master_pwd_checkbox.setChecked(True)
                    self.master_pwd_checkbox.blockSignals(False)
            except Exception:
                QMessageBox.warning(self, '验证失败', '密码验证出错，无法禁用。')
                self.master_pwd_checkbox.blockSignals(True)
                self.master_pwd_checkbox.setChecked(True)
                self.master_pwd_checkbox.blockSignals(False)

    def _on_set_master_password(self):
        try:
            from features.lock_dialog import SetMasterPasswordDialog
            dialog = SetMasterPasswordDialog(self)
            if dialog.exec_() == SetMasterPasswordDialog.Accepted:
                password = dialog.get_password()
                if password:
                    from features.encryption import NoteEncryption
                    result = NoteEncryption.hash_master_password(password)
                    self.manager.config.set('security.master_password_hash', result['hash'])
                    self.manager.config.set('security.master_password_salt', result['salt'])
                    self.manager.config.set('security.require_master_password', True)
                    self.master_pwd_checkbox.setChecked(True)
                    QMessageBox.information(self, '设置成功', '主密码已设置。')
        except Exception as e:
            QMessageBox.warning(self, '设置失败', f'设置主密码失败: {e}')

    # ==================== 云同步 ====================

    def setup_sync_tab(self, tab_widget):
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 启用同步
        self.sync_enabled_cb = QCheckBox("启用云同步")
        self.sync_enabled_cb.setChecked(self.manager.config.get('sync.enabled', False))
        self.sync_enabled_cb.stateChanged.connect(self._on_sync_enabled_changed)
        layout.addWidget(self.sync_enabled_cb)

        # 同步提供商
        provider_group = QGroupBox("同步提供商")
        provider_layout = QFormLayout()

        self.sync_provider_combo = QComboBox()
        self.sync_provider_combo.addItems(['WebDAV (坚果云/Nextcloud)', '本地文件夹 (OneDrive)'])
        provider = self.manager.config.get('sync.provider', 'webdav')
        if provider == 'local':
            self.sync_provider_combo.setCurrentIndex(1)
        self.sync_provider_combo.currentIndexChanged.connect(self._on_sync_provider_changed)
        provider_layout.addRow("提供商:", self.sync_provider_combo)
        provider_group.setLayout(provider_layout)
        layout.addWidget(provider_group)

        # WebDAV 配置
        webdav_group = QGroupBox("WebDAV 配置")
        webdav_layout = QFormLayout()

        self.webdav_url = QLineEdit()
        self.webdav_url.setText(self.manager.config.get('sync.webdav.url', ''))
        self.webdav_url.setPlaceholderText('https://dav.jianguoyun.com/dav/')
        webdav_layout.addRow("服务器 URL:", self.webdav_url)

        self.webdav_user = QLineEdit()
        self.webdav_user.setText(self.manager.config.get('sync.webdav.username', ''))
        webdav_layout.addRow("用户名:", self.webdav_user)

        self.webdav_pwd = QLineEdit()
        self.webdav_pwd.setEchoMode(QLineEdit.Password)
        webdav_layout.addRow("密码:", self.webdav_pwd)

        self.webdav_path = QLineEdit()
        self.webdav_path.setText(self.manager.config.get('sync.webdav.remote_path', '/stickynote/'))
        webdav_layout.addRow("远程路径:", self.webdav_path)

        save_webdav_btn = QPushButton("保存 WebDAV 配置")
        save_webdav_btn.clicked.connect(self._on_save_webdav)
        webdav_layout.addRow(save_webdav_btn)

        webdav_group.setLayout(webdav_layout)
        layout.addWidget(webdav_group)

        # 自动同步
        auto_sync_layout = QHBoxLayout()
        self.auto_sync_cb = QCheckBox("自动同步")
        self.auto_sync_cb.setChecked(self.manager.config.get('sync.auto_sync', False))
        self.auto_sync_cb.stateChanged.connect(self._on_auto_sync_changed)
        auto_sync_layout.addWidget(self.auto_sync_cb)

        auto_sync_layout.addWidget(QLabel("间隔:"))
        self.sync_interval_spin = QSpinBox()
        self.sync_interval_spin.setRange(5, 1440)
        self.sync_interval_spin.setValue(self.manager.config.get('sync.sync_interval_minutes', 30))
        self.sync_interval_spin.setSuffix(" 分钟")
        self.sync_interval_spin.valueChanged.connect(self._on_sync_interval_changed)
        auto_sync_layout.addWidget(self.sync_interval_spin)
        auto_sync_layout.addStretch()
        layout.addLayout(auto_sync_layout)

        layout.addStretch()
        tab_widget.setLayout(layout)

    def _on_sync_enabled_changed(self):
        self.manager.config.set('sync.enabled', self.sync_enabled_cb.isChecked())

    def _on_sync_provider_changed(self, idx):
        provider = 'local' if idx == 1 else 'webdav'
        self.manager.config.set('sync.provider', provider)

    def _on_save_webdav(self):
        self.manager.config.set('sync.webdav.url', self.webdav_url.text())
        self.manager.config.set('sync.webdav.username', self.webdav_user.text())
        self.manager.config.set('sync.webdav.password_encrypted', self.webdav_pwd.text())
        self.manager.config.set('sync.webdav.remote_path', self.webdav_path.text())
        QMessageBox.information(self, '保存成功', 'WebDAV 配置已保存。')

    def _on_auto_sync_changed(self):
        self.manager.config.set('sync.auto_sync', self.auto_sync_cb.isChecked())

    def _on_sync_interval_changed(self, val):
        self.manager.config.set('sync.sync_interval_minutes', val)

    # ==================== 插件设置 ====================

    def setup_plugins_tab(self, tab_widget):
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 启用开关
        self.plugins_enabled_cb = QCheckBox("启用插件系统")
        self.plugins_enabled_cb.setChecked(self.manager.config.get('plugins.enabled', True))
        self.plugins_enabled_cb.stateChanged.connect(self._on_plugins_enabled_changed)
        layout.addWidget(self.plugins_enabled_cb)

        # 获取已加载插件
        plugins_list = []
        if hasattr(self.manager, 'plugin_registry'):
            plugins_list = self.manager.plugin_registry.list_plugins()

        if not plugins_list:
            no_plugin = QLabel("（暂无已加载的插件）")
            no_plugin.setStyleSheet("color: #999; font-style: italic; padding: 20px;")
            no_plugin.setAlignment(Qt.AlignCenter)
            layout.addWidget(no_plugin)
        else:
            # 存储每个插件的动态控件引用
            self._plugin_config_widgets = {}

            for plugin_name, plugin in plugins_list:
                fields = plugin.get_config_fields()
                if not fields:
                    # 无配置项的插件只显示信息
                    info_group = QGroupBox(f"{plugin_name} v{plugin.version}")
                    info_layout = QVBoxLayout()
                    desc_label = QLabel(plugin.description)
                    desc_label.setWordWrap(True)
                    desc_label.setStyleSheet("color: #666;")
                    info_layout.addWidget(desc_label)
                    info_group.setLayout(info_layout)
                    layout.addWidget(info_group)
                    continue

                # 有配置项的插件
                plugin_group = QGroupBox(f"{plugin_name} v{plugin.version}")
                plugin_layout = QVBoxLayout()
                plugin_layout.setSpacing(8)

                desc_label = QLabel(plugin.description)
                desc_label.setWordWrap(True)
                desc_label.setStyleSheet("color: #666; font-size: 9pt;")
                plugin_layout.addWidget(desc_label)

                form_layout = QFormLayout()
                form_layout.setSpacing(6)

                field_widgets = {}

                for field in fields:
                    key = field['key']
                    label = field.get('label', key)
                    ftype = field.get('type', 'text')
                    default = field.get('default', '')
                    current_value = plugin.config.get(key, default)

                    if ftype == 'bool':
                        w = QCheckBox()
                        w.setChecked(bool(current_value))
                        form_layout.addRow(label, w)

                    elif ftype == 'select':
                        w = QComboBox()
                        options = field.get('options', [])
                        w.addItems([str(o) for o in options])
                        idx = w.findText(str(current_value))
                        if idx >= 0:
                            w.setCurrentIndex(idx)
                        form_layout.addRow(label, w)

                    elif ftype == 'int':
                        w = QSpinBox()
                        w.setRange(field.get('min', 0), field.get('max', 9999))
                        w.setValue(int(current_value) if current_value else default)
                        suffix = field.get('suffix', '')
                        if suffix:
                            w.setSuffix(f' {suffix}')
                        form_layout.addRow(label, w)

                    else:  # 'text' or default
                        w = QLineEdit()
                        w.setText(str(current_value))
                        w.setPlaceholderText(str(default))
                        form_layout.addRow(label, w)

                    # 帮助提示
                    help_text = field.get('help', '')
                    if help_text:
                        help_label = QLabel(f'  {help_text}')
                        help_label.setStyleSheet("color: #999; font-size: 8pt;")
                        form_layout.addRow('', help_label)

                    field_widgets[key] = (ftype, w)

                plugin_layout.addLayout(form_layout)

                # 保存按钮
                save_btn = QPushButton('保存配置')
                save_btn.setFixedWidth(100)
                save_btn.clicked.connect(
                    lambda checked, pn=plugin_name, pi=plugin, fw=field_widgets:
                    self._save_plugin_config(pn, pi, fw)
                )
                btn_row = QHBoxLayout()
                btn_row.addStretch()
                btn_row.addWidget(save_btn)
                plugin_layout.addLayout(btn_row)

                plugin_group.setLayout(plugin_layout)
                layout.addWidget(plugin_group)

                self._plugin_config_widgets[plugin_name] = (plugin, field_widgets)

        layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)
        tab_widget.setLayout(outer_layout)

    def _save_plugin_config(self, plugin_name, plugin, field_widgets):
        """保存单个插件的配置"""
        new_config = {}
        for key, (ftype, widget) in field_widgets.items():
            if ftype == 'bool':
                new_config[key] = widget.isChecked()
            elif ftype == 'select':
                new_config[key] = widget.currentText()
            elif ftype == 'int':
                new_config[key] = widget.value()
            else:
                new_config[key] = widget.text()

        # 保存到持久化存储
        self.manager.plugin_api.set_plugin_config(plugin_name, new_config)

        # 更新插件实例的 config 字典
        plugin.config.update(new_config)

        # 通知插件配置已变更
        for key, value in new_config.items():
            plugin.on_config_changed(key, value)

        QMessageBox.information(self, '配置已保存', f'{plugin_name} 的配置已保存。')

    def _on_plugins_enabled_changed(self):
        self.manager.config.set('plugins.enabled', self.plugins_enabled_cb.isChecked())

    # ==================== 快捷键设置 ====================

    def setup_shortcuts_tab(self, tab_widget):
        """构建快捷键设置标签页"""
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        hint = QLabel('自定义全局快捷键。点击“录制”后按下新的快捷键组合。')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #888;')
        layout.addWidget(hint)

        # 快捷键列表
        shortcuts_group = QGroupBox('全局快捷键')
        shortcuts_layout = QFormLayout()
        shortcuts_layout.setSpacing(10)

        # 默认快捷键定义
        default_shortcuts = {
            'add_note': ('新建便签', 'Ctrl+Shift+N'),
            'show_search_dialog': ('搜索便签', 'Ctrl+Shift+F'),
            'show_backup_dialog': ('备份管理', 'Ctrl+Shift+B'),
            'show_group_view': ('分组视图', 'Ctrl+Shift+G'),
        }

        self._shortcut_editors = {}

        for action_name, (label_text, default_combo) in default_shortcuts.items():
            # 从配置读取当前值
            current = self.manager.config.get(f'shortcuts.{action_name}', default_combo)

            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)

            combo_label = QLabel(current)
            combo_label.setFixedWidth(160)
            combo_label.setStyleSheet(
                'QLabel { background-color: #f5f5f5; border: 1px solid #ccc; '
                'border-radius: 3px; padding: 4px 8px; font-family: Consolas, monospace; }'
            )

            record_btn = QPushButton('录制')
            record_btn.setFixedSize(60, 28)

            reset_btn = QPushButton('重置')
            reset_btn.setFixedSize(50, 28)

            # 录制按钮逻辑
            def _start_record(lbl, btn, action, default):
                btn.setText('按下...')
                btn.setEnabled(False)
                self._recording_shortcut = True
                self._record_target = (lbl, btn, action, default)
                # 安装事件过滤器
                self.installEventFilter(self._ShortcutRecorder(self, lbl, btn, action))

            def _reset_shortcut(lbl, btn, action, default):
                lbl.setText(default)
                self.manager.config.set(f'shortcuts.{action}', default)
                QMessageBox.information(self, '已重置', f'快捷键已重置为 {default}')

            record_btn.clicked.connect(
                lambda checked, l=combo_label, b=record_btn, a=action_name, d=default_combo:
                _start_record(l, b, a, d)
            )
            reset_btn.clicked.connect(
                lambda checked, l=combo_label, b=record_btn, a=action_name, d=default_combo:
                _reset_shortcut(l, b, a, d)
            )

            row_layout.addWidget(combo_label)
            row_layout.addWidget(record_btn)
            row_layout.addWidget(reset_btn)
            row_layout.addStretch()

            row_widget = QWidget()
            row_widget.setLayout(row_layout)
            shortcuts_layout.addRow(f'{label_text}:', row_widget)

            self._shortcut_editors[action_name] = (combo_label, record_btn)

        shortcuts_group.setLayout(shortcuts_layout)
        layout.addWidget(shortcuts_group)

        # 提示
        note = QLabel('提示：快捷键组合必须包含 Ctrl、Shift 或 Alt 修饰键。\n'
                     '修改后需要重启应用才能生效。')
        note.setStyleSheet('color: #999; font-size: 9pt;')
        note.setWordWrap(True)
        layout.addWidget(note)

        # 保存按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        apply_btn = QPushButton('保存快捷键')
        apply_btn.setStyleSheet(
            'QPushButton { background-color: #4a86e8; color: white; padding: 6px 16px; '
            'font-weight: bold; border-radius: 4px; }'
            'QPushButton:hover { background-color: #3a76d8; }'
        )

        def _save_shortcuts():
            for action_name, (label, _) in self._shortcut_editors.items():
                self.manager.config.set(f'shortcuts.{action_name}', label.text())
            QMessageBox.information(self, '已保存', '快捷键配置已保存。重启应用后生效。')

        apply_btn.clicked.connect(_save_shortcuts)
        btn_layout.addWidget(apply_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()
        tab_widget.setLayout(layout)

    class _ShortcutRecorder(QObject):
        """快捷键录制事件过滤器"""

        def __init__(self, parent_dialog, label, button, action_name):
            super().__init__(parent_dialog)
            self.label = label
            self.button = button
            self.action_name = action_name
            self.parent_dialog = parent_dialog

        def eventFilter(self, obj, event):
            from PyQt5.QtCore import QEvent
            if event.type() == QEvent.KeyPress:
                modifiers = event.modifiers()
                key = event.key()

                # 忽略单独的修饰键
                if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
                    return True

                parts = []
                if modifiers & Qt.ControlModifier:
                    parts.append('Ctrl')
                if modifiers & Qt.ShiftModifier:
                    parts.append('Shift')
                if modifiers & Qt.AltModifier:
                    parts.append('Alt')

                # 获取按键名称
                key_text = QKeySequence(key).toString()
                if key_text:
                    parts.append(key_text)

                combo = '+'.join(parts)

                # 冲突检测
                conflict = self._check_conflict(combo)
                if conflict:
                    reply = QMessageBox.question(
                        self.parent_dialog, '快捷键冲突',
                        f'快捷键 {combo} 已被“{conflict}”使用。\n是否覆盖？',
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply != QMessageBox.Yes:
                        self.button.setText('录制')
                        self.button.setEnabled(True)
                        self.parent_dialog.removeEventFilter(self)
                        return True

                self.label.setText(combo)
                self.button.setText('录制')
                self.button.setEnabled(True)
                self.parent_dialog.removeEventFilter(self)
                return True
            return False

        def _check_conflict(self, combo: str) -> Optional[str]:
            """检查快捷键是否与其他动作冲突"""
            if not hasattr(self.parent_dialog, '_shortcut_editors'):
                return None
            for action_name, (label, _) in self.parent_dialog._shortcut_editors.items():
                if action_name != self.action_name and label.text() == combo:
                    # 查找动作名称
                    names = {
                        'add_note': '新建便签',
                        'show_search_dialog': '搜索便签',
                        'show_backup_dialog': '备份管理',
                        'show_group_view': '分组视图',
                    }
                    return names.get(action_name, action_name)
            return None


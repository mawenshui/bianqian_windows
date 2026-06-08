# -*- coding: utf-8 -*-
"""
设置对话框模块

提供主题选择和字体设置界面，使用标签页组织。
"""

import os

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QTabWidget, QLabel, QComboBox, QCheckBox,
    QPushButton, QSpinBox, QLineEdit, QTextEdit, QFrame,
    QFontComboBox, QWidget, QProgressBar
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

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

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
    QFontComboBox, QWidget
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from core import get_styles_dir


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

        main_layout = QVBoxLayout()
        main_layout.addWidget(tab_widget)

        author_label = QLabel("By\uff1aMaWenshui")
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

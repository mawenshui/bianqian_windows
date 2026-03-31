import os
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QGroupBox, QFormLayout, QLabel, QComboBox, QFontComboBox, QSpinBox, QCheckBox, QHBoxLayout, QPushButton
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

class SettingsDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowModality(Qt.NonModal)  # 设置为非模态对话框
        self.initUI()

    def initUI(self):
        self.setWindowTitle('设置')
        self.setFixedSize(600, 500)  # 增加窗口大小以容纳新功能
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)  # 始终置顶
        
        # 使用标签页布局
        tab_widget = QTabWidget()
        
        # 主题设置标签页
        theme_tab = QWidget()
        self.setup_theme_tab(theme_tab)
        tab_widget.addTab(theme_tab, "主题设置")
        
        # 字体设置标签页
        font_tab = QWidget()
        self.setup_font_tab(font_tab)
        tab_widget.addTab(font_tab, "字体设置")
        
        main_layout = QVBoxLayout()
        main_layout.addWidget(tab_widget)
        
        # 作者标签
        author_label = QLabel("By：MaWenshui")
        author_label.setAlignment(Qt.AlignCenter)
        author_label.setStyleSheet("color: gray; font-size: 10pt;")
        main_layout.addWidget(author_label)
        
        self.setLayout(main_layout)
    
    def setup_theme_tab(self, tab_widget):
        """设置主题标签页"""
        layout = QVBoxLayout()
        
        # 主题选择区域
        theme_group = QGroupBox("主题选择")
        theme_layout = QFormLayout()
        
        self.theme_label = QLabel("选择便签默认主题:")
        self.theme_combo = QComboBox()
        
        # 动态加载主题
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
        preview_group = QGroupBox("主题预览")
        preview_layout = QVBoxLayout()
        
        # 创建预览便签
        self.preview_note = QGroupBox()
        self.preview_note.setFixedSize(280, 200)
        
        preview_note_layout = QVBoxLayout()
        
        # 预览标题
        self.preview_title = QLabel("预览标题")
        self.preview_title.setStyleSheet("font-weight: bold; padding: 5px;")
        preview_note_layout.addWidget(self.preview_title)
        
        # 预览内容
        self.preview_content = QLabel("这是主题预览内容\n可以看到当前主题的样式效果")
        self.preview_content.setWordWrap(True)
        preview_note_layout.addWidget(self.preview_content)
        
        self.preview_note.setLayout(preview_note_layout)
        preview_layout.addWidget(self.preview_note)
        
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)
        
        # 更新预览
        self.update_theme_preview()
        
        tab_widget.setLayout(layout)
    
    def setup_font_tab(self, tab_widget):
        """设置字体标签页"""
        layout = QVBoxLayout()
        
        # 字体选择区域
        font_group = QGroupBox("字体设置")
        font_layout = QFormLayout()
        
        # 字体族选择
        self.font_family_combo = QFontComboBox()
        current_font = self.manager.get_default_font()
        if current_font:
            self.font_family_combo.setCurrentFont(QFont(current_font['family']))
        self.font_family_combo.currentFontChanged.connect(self.on_font_changed)
        font_layout.addRow("字体族:", self.font_family_combo)
        
        # 字体大小
        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setRange(8, 72)
        self.font_size_spinbox.setValue(current_font.get('size', 12) if current_font else 12)
        self.font_size_spinbox.setSuffix(' pt')
        self.font_size_spinbox.valueChanged.connect(self.on_font_changed)
        font_layout.addRow("字体大小:", self.font_size_spinbox)
        
        # 字体样式
        font_style_layout = QHBoxLayout()
        self.font_bold_checkbox = QCheckBox("粗体")
        self.font_italic_checkbox = QCheckBox("斜体")
        if current_font:
            self.font_bold_checkbox.setChecked(current_font.get('bold', False))
            self.font_italic_checkbox.setChecked(current_font.get('italic', False))
        self.font_bold_checkbox.stateChanged.connect(self.on_font_changed)
        self.font_italic_checkbox.stateChanged.connect(self.on_font_changed)
        font_style_layout.addWidget(self.font_bold_checkbox)
        font_style_layout.addWidget(self.font_italic_checkbox)
        font_style_layout.addStretch()
        font_layout.addRow("字体样式:", font_style_layout)
        
        font_group.setLayout(font_layout)
        layout.addWidget(font_group)
        
        # 字体预览区域
        font_preview_group = QGroupBox("字体预览")
        font_preview_layout = QVBoxLayout()
        
        self.font_preview_label = QLabel("这是字体预览文本\nABCDEFG abcdefg 12345")
        self.font_preview_label.setAlignment(Qt.AlignCenter)
        self.font_preview_label.setStyleSheet("border: 1px solid gray; padding: 20px; background-color: white;")
        self.font_preview_label.setMinimumHeight(100)
        
        font_preview_layout.addWidget(self.font_preview_label)
        font_preview_group.setLayout(font_preview_layout)
        layout.addWidget(font_preview_group)
        
        # 重置按钮
        reset_layout = QHBoxLayout()
        reset_layout.addStretch()
        reset_font_btn = QPushButton("重置为默认字体")
        reset_font_btn.clicked.connect(self.reset_font_settings)
        reset_layout.addWidget(reset_font_btn)
        layout.addLayout(reset_layout)
        
        # 更新字体预览
        self.update_font_preview()
        
        tab_widget.setLayout(layout)

    def load_themes(self):
        self.themes = self.manager.get_available_themes()
        self.theme_combo.clear()
        for theme_name in self.themes.keys():
            self.theme_combo.addItem(theme_name)

    def on_theme_changed(self):
        """主题改变时的处理"""
        selected_theme_name = self.theme_combo.currentText()
        selected_theme_css = self.themes.get(selected_theme_name, "soft_yellow.css")
        self.manager.set_default_theme(selected_theme_css)
        self.manager.apply_theme_to_all_notes()
        self.update_theme_preview()
    
    def update_theme_preview(self):
        """更新主题预览"""
        if hasattr(self, 'preview_note'):
            selected_theme_name = self.theme_combo.currentText()
            selected_theme_css = self.themes.get(selected_theme_name, "soft_yellow.css")
            
            # 读取主题CSS文件
            css_path = os.path.join('styles', selected_theme_css)
            if os.path.exists(css_path):
                with open(css_path, 'r', encoding='utf-8') as f:
                    css_content = f.read()
                
                # 应用样式到预览组件
                self.preview_note.setStyleSheet(css_content)
                self.preview_title.setStyleSheet(css_content)
                self.preview_content.setStyleSheet(css_content)
    
    def on_font_changed(self):
        """字体改变时的处理"""
        font_settings = {
            'family': self.font_family_combo.currentFont().family(),
            'size': self.font_size_spinbox.value(),
            'bold': self.font_bold_checkbox.isChecked(),
            'italic': self.font_italic_checkbox.isChecked()
        }
        
        # 保存字体设置
        self.manager.set_default_font(font_settings)
        
        # 更新字体预览
        self.update_font_preview()
        
        # 应用到所有便签
        self.manager.apply_font_to_all_notes()
    
    def update_font_preview(self):
        """更新字体预览"""
        if hasattr(self, 'font_preview_label'):
            font = QFont()
            font.setFamily(self.font_family_combo.currentFont().family())
            font.setPointSize(self.font_size_spinbox.value())
            font.setBold(self.font_bold_checkbox.isChecked())
            font.setItalic(self.font_italic_checkbox.isChecked())
            
            self.font_preview_label.setFont(font)
    
    def reset_font_settings(self):
        """重置字体设置为默认值"""
        self.font_family_combo.setCurrentFont(QFont("微软雅黑"))
        self.font_size_spinbox.setValue(12)
        self.font_bold_checkbox.setChecked(False)
        self.font_italic_checkbox.setChecked(False)
        
        # 触发字体更新
        self.on_font_changed()
    
    def change_theme(self):
        """保持向后兼容性"""
        self.on_theme_changed()

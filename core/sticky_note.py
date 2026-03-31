import sys
import os
import json
from functools import partial
from PyQt5.QtWidgets import (
    QApplication, QWidget, QTextEdit, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QMessageBox, QCheckBox,
    QColorDialog, QFrame, QDialog, QLineEdit, QListWidget, QListWidgetItem,
    QInputDialog
)
from PyQt5.QtCore import Qt, QPoint, QRect, QMimeData, QSize
from PyQt5.QtGui import QFont, QColor, QPalette, QCursor, QTextCursor

# 导入新功能模块
from features.undo_redo import UndoRedoLineEdit, UndoRedoTextEdit
from features.positioning import get_position_manager
from features.formatter import ContentFormatter

# 定义常量用于窗口调整大小
RESIZE_MARGIN = 10  # 调整大小检测边界宽度

class PlainLineEdit(UndoRedoLineEdit):
    def paste(self):
        clipboard = QApplication.clipboard()
        plain_text = clipboard.text()
        self.insert(plain_text)

    def insertFromMimeData(self, source: QMimeData):
        if source.hasText():
            self.insert(source.text())
        else:
            super().insertFromMimeData(source)

class PlainTextEdit(UndoRedoTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.formatter = ContentFormatter()
        self.auto_format_enabled = True
    
    def set_auto_format_enabled(self, enabled: bool):
        """设置是否启用自动格式化"""
        self.auto_format_enabled = enabled
    
    def paste(self):
        clipboard = QApplication.clipboard()
        if self.auto_format_enabled:
            text = clipboard.text()
            formatted_text, content_type = self.formatter.format_content(text)
            
            if content_type != 'plain':
                self.insertPlainText(formatted_text)
            else:
                self.insertPlainText(text)
        else:
            self.insertPlainText(clipboard.text())

    def insertFromMimeData(self, source: QMimeData):
        if source.hasText() and self.auto_format_enabled:
            text = source.text()
            formatted_text, content_type = self.formatter.format_content(text)
            
            if content_type != 'plain':
                self.insertPlainText(formatted_text)
            else:
                self.insertPlainText(text)
        elif source.hasText():
            self.insertPlainText(source.text())
        else:
            super().insertFromMimeData(source)

class StickyNote(QWidget):
    def __init__(self, note_id, notes_dir='notes', manager=None, theme_css="soft_yellow.css"):
        super().__init__()
        self.note_id = note_id
        self.manager = manager  # Reference to Manager
        self.is_deleted = False  # 标记便签是否已被删除

        # 将 notes_dir 转换为绝对路径，避免相对路径问题
        self.notes_dir = os.path.abspath(notes_dir)
        os.makedirs(self.notes_dir, exist_ok=True)
        self.note_file = os.path.join(self.notes_dir, f'note_{self.note_id}.json')
        self.note_data = self.load_note()

        # 如果加载的便签没有主题，则使用传入的默认主题
        self.theme = self.note_data.get('theme', theme_css)

        self.dragging = False
        self.resizing = False
        self.resize_dir = None
        self.offset = QPoint()

        self.initUI()

    def initUI(self):
        self.setWindowTitle(self.note_data.get('title', f'便签 {self.note_id}'))
        # 设置窗口标志为工具窗口，并且不在任务栏显示
        flags = Qt.Window | Qt.FramelessWindowHint
        if self.note_data.get('always_on_top', True):
            flags |= Qt.WindowStaysOnTopHint
        flags |= Qt.Tool  # 不在任务栏显示
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, False)  # 修改为不透明背景
        self.setAttribute(Qt.WA_NoSystemBackground, False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        # 设置主布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN)

        # 标题编辑（使用自定义的 PlainLineEdit）
        self.title_edit = PlainLineEdit()
        # 初始高度将在apply_font方法中根据字体大小动态设置
        self.title_edit.setFixedHeight(40)  # 临时设置，将被apply_font覆盖
        self.title_edit.setText(self.note_data.get('title', f'便签 {self.note_id}'))
        self.title_edit.textChanged.connect(self.update_title)
        self.title_edit.setMaxLength(50)  # 设置最大字符长度
        main_layout.addWidget(self.title_edit)

        # 内容编辑区域（使用自定义的 PlainTextEdit）
        self.text_edit = PlainTextEdit()
        # 优先加载富文本内容，如果不存在则加载纯文本内容
        content = self.note_data.get('content', '')
        if content and content.startswith('<!DOCTYPE') or '<html>' in content:
            # 如果是HTML格式，使用setHtml加载
            self.text_edit.setHtml(content)
        else:
            # 否则使用setText加载纯文本
            self.text_edit.setText(content)
        self.text_edit.textChanged.connect(self.update_content)
        main_layout.addWidget(self.text_edit)

        # 新增：字体大小调整按钮布局
        font_layout = QHBoxLayout()
        font_layout.setContentsMargins(0, 0, 0, 0)
        font_layout.setSpacing(5)

        self.decrease_font_btn = QPushButton('A-')
        self.decrease_font_btn.setFixedSize(40, 30)
        self.decrease_font_btn.clicked.connect(self.decrease_font_size)
        font_layout.addWidget(self.decrease_font_btn)

        self.increase_font_btn = QPushButton('A+')
        self.increase_font_btn.setFixedSize(40, 30)
        self.increase_font_btn.clicked.connect(self.increase_font_size)
        font_layout.addWidget(self.increase_font_btn)
        
        # 添加分隔符
        self.separator1 = QLabel('|')
        # 样式将在apply_theme中动态设置
        font_layout.addWidget(self.separator1)
        
        # 加粗按钮
        self.bold_btn = QPushButton('B')
        self.bold_btn.setFixedSize(30, 30)
        self.bold_btn.setCheckable(True)
        self.bold_btn.setToolTip('加粗')
        # 样式将在apply_theme中动态设置
        self.bold_btn.clicked.connect(self.toggle_bold)
        font_layout.addWidget(self.bold_btn)
        
        # 斜体按钮
        self.italic_btn = QPushButton('I')
        self.italic_btn.setFixedSize(30, 30)
        self.italic_btn.setCheckable(True)
        self.italic_btn.setToolTip('斜体')
        # 样式将在apply_theme中动态设置
        self.italic_btn.clicked.connect(self.toggle_italic)
        font_layout.addWidget(self.italic_btn)
        
        # 添加分隔符
        self.separator2 = QLabel('|')
        # 样式将在apply_theme中动态设置
        font_layout.addWidget(self.separator2)
        
        # 字体颜色按钮
        self.color_btn = QPushButton('A')
        self.color_btn.setFixedSize(30, 30)
        self.color_btn.setCheckable(True)
        self.color_btn.setToolTip('字体颜色')
        # 样式将在apply_theme中动态设置
        self.color_btn.clicked.connect(self.choose_font_color)
        font_layout.addWidget(self.color_btn)

        # 标签按钮
        self.tag_btn = QPushButton('标签')
        self.tag_btn.setFixedSize(40, 30)
        self.tag_btn.setToolTip('标签管理')
        # 样式将在apply_theme中动态设置
        self.tag_btn.clicked.connect(self.show_tag_manager)
        font_layout.addWidget(self.tag_btn)

        # 分组按钮
        self.group_btn = QPushButton('分组')
        self.group_btn.setFixedSize(40, 30)
        self.group_btn.setToolTip('分组管理')
        # 样式将在apply_theme中动态设置
        self.group_btn.clicked.connect(self.show_group_manager)
        font_layout.addWidget(self.group_btn)

        font_layout.addStretch()
        main_layout.addLayout(font_layout)

        # 标签显示区域
        self.tags_layout = QHBoxLayout()
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(5)
        self.tags_container = QWidget()
        self.tags_container.setLayout(self.tags_layout)
        main_layout.addWidget(self.tags_container)

        # 分组显示区域
        self.group_layout = QHBoxLayout()
        self.group_layout.setContentsMargins(0, 0, 0, 0)
        self.group_layout.setSpacing(5)
        self.group_container = QWidget()
        self.group_container.setLayout(self.group_layout)
        main_layout.addWidget(self.group_container)

        # 工具栏
        toolbar = QHBoxLayout()

        self.transparency_slider = QSlider(Qt.Horizontal)
        self.transparency_slider.setRange(20, 100)  # 20% 到 100%
        self.transparency_slider.setValue(int(self.note_data.get('opacity', 0.9) * 100))
        self.transparency_slider.setSingleStep(1)
        self.transparency_slider.setFixedWidth(200)  # 增加宽度以适应显示
        self.transparency_slider.valueChanged.connect(self.change_transparency)
        self.transparency_label = QLabel('透明度:')
        toolbar.addWidget(self.transparency_label)
        toolbar.addWidget(self.transparency_slider)

        self.topmost_checkbox = QCheckBox("总在最前")
        self.topmost_checkbox.setChecked(self.note_data.get('always_on_top', True))
        self.topmost_checkbox.stateChanged.connect(self.toggle_always_on_top)
        toolbar.addWidget(self.topmost_checkbox)
        
        # 格式化开关
        self.format_checkbox = QCheckBox("智能格式化")
        self.format_checkbox.setChecked(self.note_data.get('auto_format_enabled', True))
        self.format_checkbox.setToolTip('启用后粘贴JSON、HTML、Markdown等内容时会自动格式化')
        self.format_checkbox.stateChanged.connect(self.toggle_auto_format)
        toolbar.addWidget(self.format_checkbox)

        toolbar.addStretch()

        # **修改部分开始：添加“隐藏”和“删除”按钮，水平排列，无图标**
        # 创建一个水平布局，用于排列“删除”和“隐藏”按钮
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        # 删除按钮
        delete_btn = QPushButton('删除')
        delete_btn.setToolTip('删除便签')
        delete_btn.setFixedSize(60, 30)
        delete_btn.clicked.connect(self.delete_note)
        buttons_layout.addWidget(delete_btn)

        # 隐藏按钮
        hide_btn = QPushButton('隐藏')
        hide_btn.setToolTip('隐藏便签')
        hide_btn.setFixedSize(60, 30)
        hide_btn.clicked.connect(self.hide_note)
        buttons_layout.addWidget(hide_btn)

        toolbar.addLayout(buttons_layout)
        # **修改部分结束**

        main_layout.addLayout(toolbar)
        self.setLayout(main_layout)
        self.apply_theme()
        
        # 应用字体设置
        if self.manager:
            # 优先使用保存的字体设置，否则使用默认字体设置
            saved_font_settings = self.note_data.get('font_settings')
            if saved_font_settings:
                self.set_font(saved_font_settings)
            else:
                font_settings = self.manager.get_default_font()
                self.set_font(font_settings)

        # 设置字体大小（保持向后兼容）
        self.title_font_size = self.note_data.get('title_font_size', 12)  # 新增：标题字体大小
        self.content_font_size = self.note_data.get('content_font_size', 12)  # 新增：内容字体大小
        self.set_font_size(self.title_font_size, self.content_font_size)
        
        # 初始化格式按钮状态
        if hasattr(self, 'font_settings') and self.font_settings:
            self.bold_btn.setChecked(self.font_settings.get('bold', False))
            self.italic_btn.setChecked(self.font_settings.get('italic', False))
        
        # 初始化字体颜色
        if 'font_color' in self.note_data:
            self.font_color = self.note_data['font_color']
            # 如果有自定义颜色，设置按钮为选中状态
            if self.font_color != '#000000':
                self.color_btn.setChecked(True)
        else:
            self.font_color = '#000000'
        
        # 更新颜色按钮样式
        self.color_btn.setStyleSheet(f'''
            QPushButton {{
                color: {self.font_color};
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 3px;
            }}
            QPushButton:checked {{
                background-color: #007acc;
                color: white;
                border: 1px solid #005a9e;
            }}
        ''')
        
        # 初始化标签
        self.tags = self.note_data.get('tags', [])
        self.update_tags_display()
        
        # 初始化分组
        self.group = self.note_data.get('group', None)
        self.update_group_display()
        
        # 设置格式化功能状态
        auto_format_enabled = self.note_data.get('auto_format_enabled', True)
        self.text_edit.set_auto_format_enabled(auto_format_enabled)

        # 设置窗口透明度
        self.setWindowOpacity(self.note_data.get('opacity', 0.9))

        # 设置窗口位置和大小
        saved_geometry = self.note_data.get('geometry')
        if saved_geometry:
            self.setGeometry(QRect(
                saved_geometry.get('x', 100),
                saved_geometry.get('y', 100),
                saved_geometry.get('width', 400),  # 增加默认宽度
                saved_geometry.get('height', 300)
            ))
            # 注册窗口位置
            position_manager = get_position_manager()
            position_manager.register_window_position(
                self.note_id, 
                QPoint(saved_geometry.get('x', 100), saved_geometry.get('y', 100)), 
                QSize(saved_geometry.get('width', 400), saved_geometry.get('height', 300))
            )
        else:
            # 使用智能定位
            position_manager = get_position_manager()
            smart_position = position_manager.get_smart_position(self.note_id)
            self.resize(400, 300)  # 默认大小宽度调整为400
            self.move(smart_position)
            # 注册窗口位置
            position_manager.register_window_position(
                self.note_id, 
                smart_position, 
                QSize(400, 300)
            )

    def set_font_size(self, title_size, content_size):
        title_font = QFont()
        title_font.setPointSize(title_size)
        title_font.setBold(True)  # 保持标题加粗
        self.title_edit.setFont(title_font)

        content_font = QFont()
        content_font.setPointSize(content_size)
        self.text_edit.setFont(content_font)

    def increase_font_size(self):
        # 增加字体大小，使用新的字体设置系统
        if hasattr(self, 'font_settings') and self.font_settings:
            current_size = self.font_settings.get('size', 12)
            self.font_settings['size'] = current_size + 1
            self.apply_font()
            if not self.is_deleted:
                self.save_note()
        else:
            # 向后兼容：如果没有font_settings，使用旧方法
            self.title_font_size += 1
            self.content_font_size += 1
            self.set_font_size(self.title_font_size, self.content_font_size)
            self.note_data['title_font_size'] = self.title_font_size
            self.note_data['content_font_size'] = self.content_font_size
            if not self.is_deleted:
                self.save_note()

    def decrease_font_size(self):
        # 减小字体大小，使用新的字体设置系统
        if hasattr(self, 'font_settings') and self.font_settings:
            current_size = self.font_settings.get('size', 12)
            if current_size > 6:  # 最小字体大小限制
                self.font_settings['size'] = current_size - 1
                self.apply_font()
                if not self.is_deleted:
                    self.save_note()
        else:
            # 向后兼容：如果没有font_settings，使用旧方法
            if self.title_font_size > 6:
                self.title_font_size -= 1
            if self.content_font_size > 6:
                self.content_font_size -= 1
            self.set_font_size(self.title_font_size, self.content_font_size)
            self.note_data['title_font_size'] = self.title_font_size
            self.note_data['content_font_size'] = self.content_font_size
            if not self.is_deleted:
                    self.save_note()
    
    def toggle_bold(self):
        """切换加粗状态"""
        # 获取当前焦点的编辑器
        current_editor = None
        if self.text_edit.hasFocus():
            current_editor = self.text_edit
        elif self.title_edit.hasFocus():
            current_editor = self.title_edit
        else:
            current_editor = self.text_edit
        
        # 获取选中的文本
        cursor = current_editor.textCursor()
        if cursor.hasSelection():
            # 有选中文本，切换选中文本的加粗状态
            char_format = cursor.charFormat()
            current_bold = char_format.fontWeight() == QFont.Bold
            char_format.setFontWeight(QFont.Normal if current_bold else QFont.Bold)
            cursor.mergeCharFormat(char_format)
            # 更新按钮状态
            self.bold_btn.setChecked(not current_bold)
        else:
            # 没有选中文本，切换当前字符格式
            char_format = current_editor.currentCharFormat()
            current_bold = char_format.fontWeight() == QFont.Bold
            char_format.setFontWeight(QFont.Normal if current_bold else QFont.Bold)
            current_editor.setCurrentCharFormat(char_format)
            # 更新按钮状态
            self.bold_btn.setChecked(not current_bold)
        
        # 同时更新全局字体设置（保持向后兼容）
        if hasattr(self, 'font_settings') and self.font_settings:
            self.font_settings['bold'] = self.bold_btn.isChecked()
            if not self.is_deleted:
                self.save_note()
    
    def toggle_italic(self):
        """切换斜体状态"""
        # 获取当前焦点的编辑器
        current_editor = None
        if self.text_edit.hasFocus():
            current_editor = self.text_edit
        elif self.title_edit.hasFocus():
            current_editor = self.title_edit
        else:
            current_editor = self.text_edit
        
        # 获取选中的文本
        cursor = current_editor.textCursor()
        if cursor.hasSelection():
            # 有选中文本，切换选中文本的斜体状态
            char_format = cursor.charFormat()
            current_italic = char_format.fontItalic()
            char_format.setFontItalic(not current_italic)
            cursor.mergeCharFormat(char_format)
            # 更新按钮状态
            self.italic_btn.setChecked(not current_italic)
        else:
            # 没有选中文本，切换当前字符格式
            char_format = current_editor.currentCharFormat()
            current_italic = char_format.fontItalic()
            char_format.setFontItalic(not current_italic)
            current_editor.setCurrentCharFormat(char_format)
            # 更新按钮状态
            self.italic_btn.setChecked(not current_italic)
        
        # 同时更新全局字体设置（保持向后兼容）
        if hasattr(self, 'font_settings') and self.font_settings:
            self.font_settings['italic'] = self.italic_btn.isChecked()
            if not self.is_deleted:
                self.save_note()
    
    def choose_font_color(self):
        """选择字体颜色"""
        # 获取当前颜色
        current_color = getattr(self, 'font_color', '#000000')
        color = QColorDialog.getColor(QColor(current_color), self, '选择字体颜色')
        
        if color.isValid():
            color_hex = color.name()
            self.font_color = color_hex
            
            # 设置按钮为选中状态
            self.color_btn.setChecked(True)
            
            # 更新颜色按钮的显示，保持选中状态的样式
            self.color_btn.setStyleSheet(f'''
                QPushButton {{
                    color: {color_hex};
                    font-weight: bold;
                    border: 1px solid #ccc;
                    border-radius: 3px;
                }}
                QPushButton:checked {{
                    background-color: #007acc;
                    color: white;
                    border: 1px solid #005a9e;
                }}
            ''')
            
            # 获取当前焦点的编辑器
            current_editor = None
            if self.text_edit.hasFocus():
                current_editor = self.text_edit
            elif self.title_edit.hasFocus():
                current_editor = self.title_edit
            else:
                # 默认应用到内容编辑器
                current_editor = self.text_edit
            
            # 获取选中的文本
            cursor = current_editor.textCursor()
            if cursor.hasSelection():
                # 有选中文本，只对选中文本应用颜色
                char_format = cursor.charFormat()
                char_format.setForeground(QColor(color_hex))
                cursor.mergeCharFormat(char_format)
            else:
                # 没有选中文本，设置当前字符格式，影响后续输入
                char_format = current_editor.currentCharFormat()
                char_format.setForeground(QColor(color_hex))
                current_editor.setCurrentCharFormat(char_format)
            
            # 保存颜色设置
            self.note_data['font_color'] = color_hex
            if not self.is_deleted:
                self.save_note()

    def is_dark_theme(self, theme_css_content):
        """检测主题是否为深色主题"""
        import re
        # 查找StickyNote的背景色
        bg_match = re.search(r'StickyNote\s*{[^}]*background-color:\s*([^;]+);', theme_css_content)
        if bg_match:
            bg_color = bg_match.group(1).strip()
            # 简单的深色检测：检查是否包含深色关键词或RGB值
            dark_keywords = ['#2', '#3', '#4', '#5', 'black', 'dark']
            return any(keyword in bg_color.lower() for keyword in dark_keywords)
        return False
    
    def get_adaptive_control_styles(self, is_dark):
        """根据主题明暗度获取自适应控件样式"""
        if is_dark:
            # 深色主题样式
            return {
                'separator_color': '#CCCCCC',
                'button_bg': '#555555',
                'button_color': '#FFFFFF',
                'button_border': '#777777',
                'button_hover_bg': '#666666',
                'button_checked_bg': '#007acc',
                'button_checked_color': '#FFFFFF'
            }
        else:
            # 浅色主题样式
            return {
                'separator_color': '#666666',
                'button_bg': '#F0F0F0',
                'button_color': '#000000',
                'button_border': '#CCCCCC',
                'button_hover_bg': '#E0E0E0',
                'button_checked_bg': '#007acc',
                'button_checked_color': '#FFFFFF'
            }
    
    def apply_adaptive_control_styles(self, styles):
        """应用自适应控件样式"""
        # 更新分隔符和标签样式
        if hasattr(self, 'separator1'):
            self.separator1.setStyleSheet(f'color: {styles["separator_color"]}; margin: 0 5px;')
        if hasattr(self, 'separator2'):
            self.separator2.setStyleSheet(f'color: {styles["separator_color"]}; margin: 0 5px;')
        if hasattr(self, 'transparency_label'):
            self.transparency_label.setStyleSheet(f'color: {styles["separator_color"]}; margin: 0 5px;')
        
        # 更新按钮样式
        button_style_template = '''
            QPushButton {
                background-color: {bg};
                color: {color};
                border: 1px solid {border};
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: {hover_bg};
            }
            QPushButton:checked {
                background-color: {checked_bg};
                color: {checked_color};
                border: 1px solid {checked_bg};
            }
        '''
        
        # 应用到字体大小调整按钮
        font_button_style = button_style_template.format(
            bg=styles['button_bg'],
            color=styles['button_color'],
            border=styles['button_border'],
            hover_bg=styles['button_hover_bg'],
            checked_bg=styles['button_checked_bg'],
            checked_color=styles['button_checked_color']
        )
        
        if hasattr(self, 'decrease_font_btn'):
            self.decrease_font_btn.setStyleSheet(font_button_style)
        if hasattr(self, 'increase_font_btn'):
            self.increase_font_btn.setStyleSheet(font_button_style)
        
        # 应用到加粗按钮
        bold_button_style = button_style_template.format(
            bg=styles['button_bg'],
            color=styles['button_color'],
            border=styles['button_border'],
            hover_bg=styles['button_hover_bg'],
            checked_bg=styles['button_checked_bg'],
            checked_color=styles['button_checked_color']
        )
        
        if hasattr(self, 'bold_btn'):
            self.bold_btn.setStyleSheet(bold_button_style)
        
        # 应用到斜体按钮（添加斜体样式）
        italic_button_style = '''
            QPushButton {
                background-color: {bg};
                color: {color};
                border: 1px solid {border};
                border-radius: 3px;
                font-weight: bold;
                font-style: italic;
            }
            QPushButton:hover {
                background-color: {hover_bg};
            }
            QPushButton:checked {
                background-color: {checked_bg};
                color: {checked_color};
                border: 1px solid {checked_bg};
            }
        '''.format(
            bg=styles['button_bg'],
            color=styles['button_color'],
            border=styles['button_border'],
            hover_bg=styles['button_hover_bg'],
            checked_bg=styles['button_checked_bg'],
            checked_color=styles['button_checked_color']
        )
        
        if hasattr(self, 'italic_btn'):
            self.italic_btn.setStyleSheet(italic_button_style)
        
        # 应用到颜色按钮（保持红色字体特色）
        color_button_style = '''
            QPushButton {
                background-color: {bg};
                color: red;
                border: 1px solid {border};
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: {hover_bg};
            }
            QPushButton:checked {
                background-color: {checked_bg};
                color: {checked_color};
                border: 1px solid {checked_bg};
            }
        '''.format(
            bg=styles['button_bg'],
            border=styles['button_border'],
            hover_bg=styles['button_hover_bg'],
            checked_bg=styles['button_checked_bg'],
            checked_color=styles['button_checked_color']
        )
        
        if hasattr(self, 'color_btn'):
            self.color_btn.setStyleSheet(color_button_style)

    def apply_theme(self):
        # 获取主题CSS文件路径
        theme_css_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'styles', self.theme)
        if not os.path.exists(theme_css_file):
            QMessageBox.warning(self, '样式加载错误', f'无法找到样式文件: {self.theme}')
            return

        # 读取CSS内容
        try:
            with open(theme_css_file, 'r', encoding='utf-8') as f:
                style = f.read()
                self.setStyleSheet(style)
                self.text_edit.setStyleSheet(style)
                self.title_edit.setStyleSheet(style)
                
                # 检测主题明暗度并应用自适应控件样式
                is_dark = self.is_dark_theme(style)
                adaptive_styles = self.get_adaptive_control_styles(is_dark)
                self.apply_adaptive_control_styles(adaptive_styles)
                
                # 重新应用字体设置，确保字体设置不被主题覆盖
                if hasattr(self, 'font_settings') and self.font_settings:
                    self.apply_font()
        except Exception as e:
            QMessageBox.warning(self, '样式加载错误', f'无法加载样式文件: {e}')

    def load_note(self):
        if os.path.exists(self.note_file):
            try:
                with open(self.note_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                QMessageBox.warning(self, '加载错误', f'无法加载便签文件: {e}')
                return self.default_note_data()
        else:
            return self.default_note_data()

    def default_note_data(self):
        return {
            'title': f'便签 {self.note_id}',
            'content': '',
            'plain_content': '',  # 新增：纯文本内容备份
            'opacity': 0.9,
            'always_on_top': True,
            'geometry': None,  # 修改为 None 以便在 initUI 中判断是否需要居中
            'theme': "soft_yellow.css",
            'title_font_size': 12,  # 新增：标题字体大小
            'content_font_size': 12,  # 新增：内容字体大小
            'auto_format_enabled': True,  # 新增：自动格式化开关
            'font_color': '#000000',  # 新增：默认字体颜色
            'tags': [],  # 新增：标签
            'group': None  # 新增：分组
        }

    def save_note(self):
        # 保存窗口几何信息
        geometry = self.geometry()
        self.note_data['geometry'] = {
            'x': geometry.x(),
            'y': geometry.y(),
            'width': geometry.width(),
            'height': geometry.height()
        }
        self.note_data['title'] = self.title_edit.text().strip() or f'便签 {self.note_id}'
        # 保存富文本内容以保留格式
        self.note_data['content'] = self.text_edit.toHtml()
        # 同时保存纯文本内容作为备用
        self.note_data['plain_content'] = self.text_edit.toPlainText()
        self.note_data['opacity'] = self.windowOpacity()
        self.note_data['always_on_top'] = self.topmost_checkbox.isChecked()
        self.note_data['theme'] = self.theme
        # 保存字体大小（如果存在）
        if hasattr(self, 'title_font_size'):
            self.note_data['title_font_size'] = self.title_font_size
        if hasattr(self, 'content_font_size'):
            self.note_data['content_font_size'] = self.content_font_size
        
        # 保存字体设置（如果存在）
        if hasattr(self, 'font_settings') and self.font_settings:
            self.note_data['font_settings'] = self.font_settings
        self.note_data['auto_format_enabled'] = self.format_checkbox.isChecked()  # 保存格式化开关状态
        try:
            with open(self.note_file, 'w', encoding='utf-8') as f:
                json.dump(self.note_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            QMessageBox.warning(self, '保存错误', f'无法保存便签文件: {e}')

    def update_title(self):
        self.setWindowTitle(self.title_edit.text().strip() or f'便签 {self.note_id}')
        if not self.is_deleted:
            self.save_note()
        if self.manager:
            self.manager.update_tray_menu()

    def update_content(self):
        if not self.is_deleted:
            self.save_note()

    def change_transparency(self, value):
        opacity = value / 100.0
        self.setWindowOpacity(opacity)
        if not self.is_deleted:
            self.save_note()

    def toggle_always_on_top(self, state):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.topmost_checkbox.isChecked())
        self.show()
        if not self.is_deleted:
            self.save_note()
    
    def toggle_auto_format(self, state):
        """切换自动格式化功能"""
        enabled = self.format_checkbox.isChecked()
        self.text_edit.set_auto_format_enabled(enabled)
        if not self.is_deleted:
            self.save_note()

    def delete_note(self):
        reply = QMessageBox.question(
            self, '删除便签',
            f"确定要删除便签 '{self.note_data.get('title', '')}' 吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                # 打印要删除的文件路径用于调试
                print(f"尝试删除文件: {self.note_file}")

                # 检查文件是否存在
                if os.path.exists(self.note_file):
                    # 确保文件未被占用
                    try:
                        with open(self.note_file, 'a'):
                            pass  # 只是尝试以追加模式打开文件
                    except Exception as e:
                        QMessageBox.warning(self, '删除失败', f'文件被占用，无法删除: {e}')
                        return

                    os.remove(self.note_file)
                    QMessageBox.information(self, '删除成功', '便签及其文件已被删除。')
                else:
                    QMessageBox.warning(self, '删除失败', '便签文件不存在。')

                if self.manager:
                    self.manager.remove_note(self.note_id)

                # 设置删除标志为 True，防止在关闭时重新保存
                self.is_deleted = True
                self.close()
            except Exception as e:
                QMessageBox.warning(self, '删除错误', f'无法删除便签文件: {e}')

    # **修改方法名称：将 close_note 改为 hide_note**
    def hide_note(self):
        self.hide()
    # **修改方法结束**

    # 实现拖动和调整大小功能
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            widget = self.childAt(event.pos())
            if widget in [self.title_edit, self.text_edit]:
                # 如果点击在输入框上，交给输入框处理
                super().mousePressEvent(event)
                return

            self.drag_pos = event.globalPos()
            self.initial_geometry = self.geometry()

            # 检查是否在调整大小区域
            rect = self.rect()
            x = event.x()
            y = event.y()
            margin = RESIZE_MARGIN
            self.resize_dir = None

            if x < margin and y < margin:
                self.resizing = True
                self.resize_dir = 'top_left'
            elif x > rect.width() - margin and y < margin:
                self.resizing = True
                self.resize_dir = 'top_right'
            elif x < margin and y > rect.height() - margin:
                self.resizing = True
                self.resize_dir = 'bottom_left'
            elif x > rect.width() - margin and y > rect.height() - margin:
                self.resizing = True
                self.resize_dir = 'bottom_right'
            elif x < margin:
                self.resizing = True
                self.resize_dir = 'left'
            elif x > rect.width() - margin:
                self.resizing = True
                self.resize_dir = 'right'
            elif y < margin:
                self.resizing = True
                self.resize_dir = 'top'
            elif y > rect.height() - margin:
                self.resizing = True
                self.resize_dir = 'bottom'
            else:
                self.dragging = True
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        widget = self.childAt(event.pos())
        if widget in [self.title_edit, self.text_edit]:
            # 如果鼠标在输入框上移动，交给输入框处理
            super().mouseMoveEvent(event)
            return

        if self.resizing:
            self.perform_resize(event.globalPos())
        elif self.dragging:
            delta = event.globalPos() - self.drag_pos
            self.move(self.initial_geometry.topLeft() + delta)
        else:
            self.update_cursor(event)
        event.accept()

    def mouseReleaseEvent(self, event):
        widget = self.childAt(event.pos())
        if widget in [self.title_edit, self.text_edit]:
            # 如果释放在输入框上，交给输入框处理
            super().mouseReleaseEvent(event)
            return

        self.dragging = False
        self.resizing = False
        self.resize_dir = None
        self.setCursor(QCursor(Qt.ArrowCursor))
        if not self.is_deleted:
            self.save_note()
        event.accept()

    def perform_resize(self, global_pos):
        delta = global_pos - self.drag_pos
        geometry = QRect(self.initial_geometry)

        min_width = 150
        min_height = 150

        if self.resize_dir == 'top_left':
            new_x = geometry.x() + delta.x()
            new_y = geometry.y() + delta.y()
            new_width = geometry.width() - delta.x()
            new_height = geometry.height() - delta.y()
            if new_width >= min_width and new_height >= min_height:
                geometry.setX(new_x)
                geometry.setY(new_y)
                geometry.setWidth(new_width)
                geometry.setHeight(new_height)
        elif self.resize_dir == 'top_right':
            new_y = geometry.y() + delta.y()
            new_width = geometry.width() + delta.x()
            new_height = geometry.height() - delta.y()
            if new_width >= min_width and new_height >= min_height:
                geometry.setY(new_y)
                geometry.setWidth(new_width)
                geometry.setHeight(new_height)
        elif self.resize_dir == 'bottom_left':
            new_x = geometry.x() + delta.x()
            new_width = geometry.width() - delta.x()
            new_height = geometry.height() + delta.y()
            if new_width >= min_width and new_height >= min_height:
                geometry.setX(new_x)
                geometry.setWidth(new_width)
                geometry.setHeight(new_height)
        elif self.resize_dir == 'bottom_right':
            new_width = geometry.width() + delta.x()
            new_height = geometry.height() + delta.y()
            if new_width >= min_width and new_height >= min_height:
                geometry.setWidth(new_width)
                geometry.setHeight(new_height)
        elif self.resize_dir == 'left':
            new_x = geometry.x() + delta.x()
            new_width = geometry.width() - delta.x()
            if new_width >= min_width:
                geometry.setX(new_x)
                geometry.setWidth(new_width)
        elif self.resize_dir == 'right':
            new_width = geometry.width() + delta.x()
            if new_width >= min_width:
                geometry.setWidth(new_width)
        elif self.resize_dir == 'top':
            new_y = geometry.y() + delta.y()
            new_height = geometry.height() - delta.y()
            if new_height >= min_height:
                geometry.setY(new_y)
                geometry.setHeight(new_height)
        elif self.resize_dir == 'bottom':
            new_height = geometry.height() + delta.y()
            if new_height >= min_height:
                geometry.setHeight(new_height)

        self.setGeometry(geometry)
        if not self.is_deleted:
            self.save_note()

    def update_cursor(self, event):
        rect = self.rect()
        margin = RESIZE_MARGIN
        x = event.x()
        y = event.y()

        # 定义区域
        top = y < margin
        bottom = y > rect.height() - margin
        left = x < margin
        right = x > rect.width() - margin

        if top and left:
            self.setCursor(QCursor(Qt.SizeFDiagCursor))  # 左上角
        elif top and right:
            self.setCursor(QCursor(Qt.SizeBDiagCursor))  # 右上角
        elif bottom and left:
            self.setCursor(QCursor(Qt.SizeBDiagCursor))  # 左下角
        elif bottom and right:
            self.setCursor(QCursor(Qt.SizeFDiagCursor))  # 右下角
        elif left:
            self.setCursor(QCursor(Qt.SizeHorCursor))  # 左边
        elif right:
            self.setCursor(QCursor(Qt.SizeHorCursor))  # 右边
        elif top:
            self.setCursor(QCursor(Qt.SizeVerCursor))  # 上边
        elif bottom:
            self.setCursor(QCursor(Qt.SizeVerCursor))  # 下边
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))
    
    def enterEvent(self, event):
        """鼠标进入窗口时的事件处理"""
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """鼠标离开窗口时恢复默认光标"""
        if not self.resizing and not self.dragging:
            self.setCursor(QCursor(Qt.ArrowCursor))
        super().leaveEvent(event)

    # 绘制边框
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        pen = QPen(QColor(200, 200, 200))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRect(0, 0, self.width()-1, self.height()-1)

    # **修改部分开始：重写 closeEvent 方法，使其在非删除情况下隐藏窗口**
    def closeEvent(self, event):
        if self.is_deleted:
            # 注销窗口位置
            position_manager = get_position_manager()
            position_manager.unregister_window_position(
                self.note_id, 
                QPoint(self.x(), self.y()), 
                QSize(self.width(), self.height())
            )
            super().closeEvent(event)
        else:
            event.ignore()
            self.hide()
            # 可选：显示系统托盘提示
            if self.manager:
                self.manager.tray_icon.showMessage(
                    "便签已隐藏",
                    f"便签 '{self.note_data.get('title', '')}' 已被隐藏。",
                    QSystemTrayIcon.Information,
                    2000
                )
    # **修改部分结束**

    # **新增方法开始：设置主题**
    def set_theme(self, theme_css):
        self.theme = theme_css
        self.apply_theme()
        if not self.is_deleted:
            self.save_note()
    
    def set_font(self, font_settings):
        """设置字体"""
        self.font_settings = font_settings
        self.apply_font()
        if not self.is_deleted:
            self.save_note()
    
    def apply_font(self):
        """应用字体设置"""
        # 获取字体设置，如果没有则使用默认值
        font_settings = getattr(self, 'font_settings', {
            'family': '微软雅黑',
            'size': 12,
            'bold': False,
            'italic': False
        })
        
        if font_settings:
            # 构建字体样式字符串
            font_family = font_settings.get('family', '微软雅黑')
            font_size = font_settings.get('size', 12)
            font_weight = 'bold' if font_settings.get('bold', False) else 'normal'
            font_style = 'italic' if font_settings.get('italic', False) else 'normal'
            
            # 获取字体颜色
            font_color = getattr(self, 'font_color', '#000000')
            
            # 直接为每个控件设置样式，使用!important确保优先级
            font_style_sheet = f"""
            font-family: "{font_family}" !important;
            font-size: {font_size}pt !important;
            font-weight: {font_weight} !important;
            font-style: {font_style} !important;
            color: {font_color} !important;
            """
            
            # 应用到文本编辑器和标题编辑器
            self.text_edit.setStyleSheet(self.text_edit.styleSheet() + font_style_sheet)
            self.title_edit.setStyleSheet(self.title_edit.styleSheet() + font_style_sheet)
            
            # 动态调整标题栏高度以适应字体大小
            # 基础高度 + 字体大小的倍数，确保有足够空间显示字体
            base_height = 30  # 基础高度
            font_height_factor = 2.5  # 字体高度倍数
            calculated_height = max(base_height, int(font_size * font_height_factor))
            
            # 设置标题编辑器的新高度
            self.title_edit.setFixedHeight(calculated_height)
            
            # 应用富文本格式到编辑器的当前字符格式
            self.apply_rich_text_format()
    
    def apply_rich_text_format(self):
        """应用富文本格式设置到编辑器"""
        # 获取字体设置
        font_settings = getattr(self, 'font_settings', {})
        font_color = getattr(self, 'font_color', '#000000')
        
        # 为文本编辑器设置默认字符格式
        text_char_format = QTextCharFormat()
        if font_settings:
            font = QFont()
            font.setFamily(font_settings.get('family', '微软雅黑'))
            font.setPointSize(font_settings.get('size', 12))
            font.setBold(font_settings.get('bold', False))
            font.setItalic(font_settings.get('italic', False))
            text_char_format.setFont(font)
        text_char_format.setForeground(QColor(font_color))
        self.text_edit.setCurrentCharFormat(text_char_format)
        
        # 为标题编辑器设置默认字符格式
        title_char_format = QTextCharFormat()
        if font_settings:
            title_font = QFont()
            title_font.setFamily(font_settings.get('family', '微软雅黑'))
            title_font.setPointSize(font_settings.get('size', 12))
            title_font.setBold(font_settings.get('bold', False))
            title_font.setItalic(font_settings.get('italic', False))
            title_char_format.setFont(title_font)
        title_char_format.setForeground(QColor(font_color))
        
        # 应用到标题编辑器（QLineEdit需要特殊处理）
        title_palette = self.title_edit.palette()
        title_palette.setColor(QPalette.Text, QColor(font_color))
        self.title_edit.setPalette(title_palette)
    
    def show_tag_manager(self):
        """显示标签管理对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle('标签管理')
        dialog.setFixedSize(400, 300)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        
        # 标签列表
        self.tag_list = QListWidget()
        layout.addWidget(self.tag_list)
        
        # 加载所有标签
        if self.manager and hasattr(self.manager, 'tag_manager'):
            all_tags = self.manager.tag_manager.get_all_tags()
            for tag in all_tags:
                item = QListWidgetItem(tag)
                # 如果标签已应用到当前便签，设置为选中状态
                if tag in self.tags:
                    item.setCheckState(Qt.Checked)
                else:
                    item.setCheckState(Qt.Unchecked)
                self.tag_list.addItem(item)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 新建标签按钮
        new_tag_btn = QPushButton('新建标签')
        new_tag_btn.clicked.connect(partial(self.create_new_tag, dialog))
        button_layout.addWidget(new_tag_btn)
        
        # 保存按钮
        save_btn = QPushButton('保存')
        save_btn.clicked.connect(partial(self.save_tags, dialog))
        button_layout.addWidget(save_btn)
        
        # 取消按钮
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(dialog.close)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        dialog.exec_()
    
    def create_new_tag(self, dialog):
        """创建新标签"""
        tag_name, ok = QInputDialog.getText(self, '新建标签', '请输入标签名称:')
        if ok and tag_name.strip():
            tag_name = tag_name.strip()
            if self.manager and hasattr(self.manager, 'tag_manager'):
                self.manager.tag_manager.add_tag(tag_name)
                # 更新标签列表
                self.tag_list.clear()
                all_tags = self.manager.tag_manager.get_all_tags()
                for tag in all_tags:
                    item = QListWidgetItem(tag)
                    if tag in self.tags:
                        item.setCheckState(Qt.Checked)
                    else:
                        item.setCheckState(Qt.Unchecked)
                    self.tag_list.addItem(item)
    
    def save_tags(self, dialog):
        """保存标签选择"""
        new_tags = []
        for i in range(self.tag_list.count()):
            item = self.tag_list.item(i)
            if item.checkState() == Qt.Checked:
                new_tags.append(item.text())
        
        # 更新便签的标签
        self.tags = new_tags
        self.note_data['tags'] = new_tags
        
        # 更新标签管理器中的标签计数
        if self.manager and hasattr(self.manager, 'tag_manager'):
            # 先移除旧标签的计数
            for old_tag in self.note_data.get('tags', []):
                self.manager.tag_manager.update_tag_count(old_tag, increment=False)
            # 再添加新标签的计数
            for new_tag in new_tags:
                self.manager.tag_manager.add_tag(new_tag)  # 确保标签存在
                self.manager.tag_manager.update_tag_count(new_tag, increment=True)
        
        # 保存便签
        if not self.is_deleted:
            self.save_note()
        
        # 更新标签显示
        self.update_tags_display()
        
        dialog.close()
    
    def update_tags_display(self):
        """更新标签显示"""
        # 清空现有标签
        while self.tags_layout.count() > 0:
            widget = self.tags_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        
        # 添加新标签
        for tag in self.tags:
            tag_label = QLabel(f'#{tag}')
            tag_label.setStyleSheet('''
                QLabel {
                    background-color: #e3f2fd;
                    color: #1976d2;
                    padding: 2px 8px;
                    border-radius: 12px;
                    font-size: 10pt;
                }
            ''')
            self.tags_layout.addWidget(tag_label)
        
        # 添加拉伸空间
        self.tags_layout.addStretch()
    
    def show_group_manager(self):
        """显示分组管理对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle('分组管理')
        dialog.setFixedSize(400, 300)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        
        # 分组列表
        self.group_list = QListWidget()
        layout.addWidget(self.group_list)
        
        # 加载所有分组
        if self.manager and hasattr(self.manager, 'group_manager'):
            all_groups = self.manager.group_manager.get_all_groups()
            for group in all_groups:
                item = QListWidgetItem(group)
                # 如果当前便签属于该分组，设置为选中状态
                if self.group == group:
                    item.setCheckState(Qt.Checked)
                else:
                    item.setCheckState(Qt.Unchecked)
                self.group_list.addItem(item)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 新建分组按钮
        new_group_btn = QPushButton('新建分组')
        new_group_btn.clicked.connect(partial(self.create_new_group, dialog))
        button_layout.addWidget(new_group_btn)
        
        # 保存按钮
        save_btn = QPushButton('保存')
        save_btn.clicked.connect(partial(self.save_group, dialog))
        button_layout.addWidget(save_btn)
        
        # 取消按钮
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(dialog.close)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        dialog.exec_()
    
    def create_new_group(self, dialog):
        """创建新分组"""
        group_name, ok = QInputDialog.getText(self, '新建分组', '请输入分组名称:')
        if ok and group_name.strip():
            group_name = group_name.strip()
            if self.manager and hasattr(self.manager, 'group_manager'):
                self.manager.group_manager.add_group(group_name)
                # 更新分组列表
                self.group_list.clear()
                all_groups = self.manager.group_manager.get_all_groups()
                for group in all_groups:
                    item = QListWidgetItem(group)
                    if self.group == group:
                        item.setCheckState(Qt.Checked)
                    else:
                        item.setCheckState(Qt.Unchecked)
                    self.group_list.addItem(item)
    
    def save_group(self, dialog):
        """保存分组选择"""
        selected_group = None
        for i in range(self.group_list.count()):
            item = self.group_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_group = item.text()
                break
        
        # 更新便签的分组
        if self.manager and hasattr(self.manager, 'group_manager'):
            if selected_group:
                self.manager.group_manager.add_note_to_group(self.note_id, selected_group)
                self.group = selected_group
                self.note_data['group'] = selected_group
            else:
                # 移除分组
                self.manager.group_manager.remove_note_from_group(self.note_id)
                self.group = None
                if 'group' in self.note_data:
                    del self.note_data['group']
        
        # 保存便签
        if not self.is_deleted:
            self.save_note()
        
        # 更新分组显示
        self.update_group_display()
        
        dialog.close()
    
    def update_group_display(self):
        """更新分组显示"""
        # 清空现有分组
        while self.group_layout.count() > 0:
            widget = self.group_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        
        # 添加分组信息
        if self.group:
            group_label = QLabel(f'📁 {self.group}')
            group_label.setStyleSheet('''
                QLabel {
                    background-color: #e8f5e8;
                    color: #2e7d32;
                    padding: 2px 8px;
                    border-radius: 12px;
                    font-size: 10pt;
                }
            ''')
            self.group_layout.addWidget(group_label)
        
        # 添加拉伸空间
        self.group_layout.addStretch()
     # **新增方法结束**
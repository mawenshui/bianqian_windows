import sys
import os
import json
from functools import partial
from PyQt5.QtWidgets import (
    QApplication, QWidget, QTextEdit, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QMessageBox, QCheckBox,
    QColorDialog, QFrame, QDialog, QLineEdit, QListWidget, QListWidgetItem,
    QInputDialog, QSystemTrayIcon, QFileDialog, QDateTimeEdit, QComboBox
)
from PyQt5.QtCore import Qt, QPoint, QRect, QMimeData, QSize, QDateTime, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QPalette, QCursor, QTextCursor, QTextCharFormat, QPainter, QPen, QTextDocument

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
        self._initial_version_saved = False  # 标记是否已保存初始版本

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

        # 待办事项按钮
        self.todo_btn = QPushButton('待办')
        self.todo_btn.setFixedSize(40, 30)
        self.todo_btn.setToolTip('待办事项')
        # 样式将在apply_theme中动态设置
        self.todo_btn.clicked.connect(self.add_todo_item)
        font_layout.addWidget(self.todo_btn)

        # 代码高亮按钮
        self.code_btn = QPushButton('代码')
        self.code_btn.setFixedSize(40, 30)
        self.code_btn.setToolTip('代码高亮')
        # 样式将在apply_theme中动态设置
        self.code_btn.clicked.connect(self.toggle_code_highlight)
        font_layout.addWidget(self.code_btn)

        # 图片插入按钮
        self.image_btn = QPushButton('图片')
        self.image_btn.setFixedSize(40, 30)
        self.image_btn.setToolTip('插入本地图片')
        # 样式将在apply_theme中动态设置
        self.image_btn.clicked.connect(self.insert_local_image)
        font_layout.addWidget(self.image_btn)

        # 文件链接按钮
        self.link_btn = QPushButton('链接')
        self.link_btn.setFixedSize(40, 30)
        self.link_btn.setToolTip('添加本地文件链接')
        # 样式将在apply_theme中动态设置
        self.link_btn.clicked.connect(self.add_local_file_link)
        font_layout.addWidget(self.link_btn)

        # 提醒按钮
        self.reminder_btn = QPushButton('提醒')
        self.reminder_btn.setFixedSize(40, 30)
        self.reminder_btn.setToolTip('设置提醒')
        # 样式将在apply_theme中动态设置
        self.reminder_btn.clicked.connect(self.set_reminder)
        font_layout.addWidget(self.reminder_btn)

        # 查找按钮
        self.find_btn = QPushButton('查找')
        self.find_btn.setFixedSize(40, 30)
        self.find_btn.setToolTip('查找和替换')
        # 样式将在apply_theme中动态设置
        self.find_btn.clicked.connect(self.show_find_replace)
        font_layout.addWidget(self.find_btn)

        # 阅读模式按钮
        self.read_mode_btn = QPushButton('阅读')
        self.read_mode_btn.setFixedSize(40, 30)
        self.read_mode_btn.setToolTip('阅读模式')
        # 样式将在apply_theme中动态设置
        self.read_mode_btn.clicked.connect(self.toggle_read_mode)
        font_layout.addWidget(self.read_mode_btn)

        # 版本历史按钮
        self.history_btn = QPushButton('历史')
        self.history_btn.setFixedSize(40, 30)
        self.history_btn.setToolTip('版本历史')
        # 样式将在apply_theme中动态设置
        self.history_btn.clicked.connect(self.show_version_history)
        font_layout.addWidget(self.history_btn)

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

        # 字数统计
        self.word_count_label = QLabel('字数: 0')
        toolbar.addWidget(self.word_count_label)

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
        
        # 初始化字数统计
        self.update_word_count()

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
            
            # 保存版本历史（首次保存或内容变化时）
            if self.manager and hasattr(self.manager, 'version_history_manager'):
                if not self._initial_version_saved:
                    # 首次保存，保存初始版本
                    self.manager.version_history_manager.save_version(
                        self.note_id, 
                        self.note_data.copy(), 
                        '初始版本'
                    )
                    self._initial_version_saved = True
                else:
                    # 检查内容是否有显著变化
                    # 可以添加更智能的版本保存逻辑，比如每隔一定时间或内容变化较大时
                    pass
        except Exception as e:
            QMessageBox.warning(self, '保存错误', f'无法保存便签文件: {e}')
    
    def show_version_history(self):
        """显示版本历史"""
        if self.manager and hasattr(self.manager, 'version_history_manager'):
            self.manager.version_history_manager.show_version_history_dialog(self.note_id)

    def update_title(self):
        self.setWindowTitle(self.title_edit.text().strip() or f'便签 {self.note_id}')
        if not self.is_deleted:
            self.save_note()
        if self.manager:
            self.manager.update_tray_menu()

    def update_content(self):
        # 更新字数统计
        self.update_word_count()
        if not self.is_deleted:
            self.save_note()
    
    def update_word_count(self):
        """更新字数统计"""
        text = self.text_edit.toPlainText()
        char_count = len(text)
        word_count = len(text.split())
        self.word_count_label.setText(f'字数: {word_count} | 字符: {char_count}')

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
            f"确定要删除便签 '{self.note_data.get('title', '')}' 吗？\n\n便签将被移动到回收站，可以在那里恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                # 先保存当前便签
                self.save_note()
                
                # 移动到回收站
                if self.manager and hasattr(self.manager, 'trash_manager'):
                    # 复制note_data
                    note_data_copy = self.note_data.copy()
                    
                    # 移动到回收站
                    self.manager.trash_manager.move_to_trash(self.note_id, note_data_copy)
                
                # 删除便签文件
                if os.path.exists(self.note_file):
                    # 确保文件未被占用
                    try:
                        with open(self.note_file, 'a'):
                            pass  # 只是尝试以追加模式打开文件
                    except Exception as e:
                        QMessageBox.warning(self, '删除失败', f'文件被占用，无法删除: {e}')
                        return

                    os.remove(self.note_file)
                
                QMessageBox.information(self, '删除成功', '便签已移动到回收站。')

                if self.manager:
                    self.manager.remove_note(self.note_id)

                # 设置删除标志为 True，防止在关闭时重新保存
                self.is_deleted = True
                self.close()
            except Exception as e:
                QMessageBox.warning(self, '删除错误', f'无法删除便签文件: {e}')

    # **修改方法名称：将 close_note 改为 hide_note**
    def hide_note(self):
        """隐藏便签（带动画）"""
        self.animate_close()
    
    def show(self):
        """显示便签（带动画）"""
        super().show()
        self.animate_open()
    
    def animate_open(self):
        """打开动画"""
        # 创建动画
        animation = QPropertyAnimation(self, b"windowOpacity")
        animation.setDuration(300)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start()
    
    def animate_close(self):
        """关闭动画"""
        # 创建动画
        animation = QPropertyAnimation(self, b"windowOpacity")
        animation.setDuration(300)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.InCubic)
        # 动画结束后隐藏窗口
        animation.finished.connect(self.hide)
        animation.start()
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
        dialog.setFixedSize(450, 350)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        
        # 标签列表
        self.tag_list = QListWidget()
        self.tag_list.itemDoubleClicked.connect(partial(self.edit_tag_color, dialog))
        layout.addWidget(self.tag_list)
        
        # 加载所有标签
        self._populate_tag_list()
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 新建标签按钮
        new_tag_btn = QPushButton('新建标签')
        new_tag_btn.clicked.connect(partial(self.create_new_tag, dialog))
        button_layout.addWidget(new_tag_btn)
        
        # 编辑标签颜色按钮
        edit_color_btn = QPushButton('编辑颜色')
        edit_color_btn.clicked.connect(partial(self.edit_selected_tag_color, dialog))
        button_layout.addWidget(edit_color_btn)
        
        # 删除标签按钮
        delete_tag_btn = QPushButton('删除标签')
        delete_tag_btn.clicked.connect(partial(self.delete_selected_tag, dialog))
        button_layout.addWidget(delete_tag_btn)
        
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
    
    def _populate_tag_list(self):
        """填充标签列表"""
        self.tag_list.clear()
        if self.manager and hasattr(self.manager, 'tag_manager'):
            all_tags = self.manager.tag_manager.get_all_tags()
            for tag in all_tags:
                item = QListWidgetItem(tag)
                tag_info = self.manager.tag_manager.get_tag_info(tag)
                if tag_info and 'color' in tag_info:
                    item.setForeground(QColor(tag_info['color']))
                # 如果标签已应用到当前便签，设置为选中状态
                if tag in self.tags:
                    item.setCheckState(Qt.Checked)
                else:
                    item.setCheckState(Qt.Unchecked)
                self.tag_list.addItem(item)
    
    def create_new_tag(self, dialog):
        """创建新标签"""
        tag_name, ok = QInputDialog.getText(self, '新建标签', '请输入标签名称:')
        if ok and tag_name.strip():
            tag_name = tag_name.strip()
            if self.manager and hasattr(self.manager, 'tag_manager'):
                self.manager.tag_manager.add_tag(tag_name)
                
                # 询问标签颜色
                color = QColorDialog.getColor(QColor('#3498db'), self, '选择标签颜色')
                if color.isValid():
                    self.manager.tag_manager.update_tag_color(tag_name, color.name())
                
                self._populate_tag_list()
    
    def edit_tag_color(self, item, dialog):
        """编辑标签颜色"""
        tag_name = item.text()
        if self.manager and hasattr(self.manager, 'tag_manager'):
            tag_info = self.manager.tag_manager.get_tag_info(tag_name)
            current_color = QColor(tag_info['color']) if tag_info and 'color' in tag_info else QColor('#3498db')
            
            color = QColorDialog.getColor(current_color, self, '选择标签颜色')
            if color.isValid():
                self.manager.tag_manager.update_tag_color(tag_name, color.name())
                self._populate_tag_list()
    
    def edit_selected_tag_color(self, dialog):
        """编辑选中标签的颜色"""
        current_item = self.tag_list.currentItem()
        if current_item:
            self.edit_tag_color(current_item, dialog)
    
    def delete_selected_tag(self, dialog):
        """删除选中的标签"""
        current_item = self.tag_list.currentItem()
        if current_item:
            tag_name = current_item.text()
            reply = QMessageBox.question(
                self,
                '确认删除',
                f'确定要删除标签 "{tag_name}" 吗？\n这不会影响已添加该标签的便签。',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes and self.manager and hasattr(self.manager, 'tag_manager'):
                self.manager.tag_manager.remove_tag(tag_name)
                self._populate_tag_list()
    
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
            
            # 获取标签颜色
            bg_color = '#e3f2fd'
            text_color = '#1976d2'
            if self.manager and hasattr(self.manager, 'tag_manager'):
                tag_info = self.manager.tag_manager.get_tag_info(tag)
                if tag_info and 'color' in tag_info:
                    custom_color = tag_info['color']
                    # 基于自定义颜色计算互补色作为背景
                    bg_color = self._get_background_color_for_tag(custom_color)
                    text_color = custom_color
            
            tag_label.setStyleSheet(f'''
                QLabel {{
                    background-color: {bg_color};
                    color: {text_color};
                    padding: 2px 8px;
                    border-radius: 12px;
                    font-size: 10pt;
                }}
            ''')
            self.tags_layout.addWidget(tag_label)
        
        # 添加拉伸空间
        self.tags_layout.addStretch()
    
    def _get_background_color_for_tag(self, text_color):
        """根据标签文字颜色获取合适的背景色"""
        # 将十六进制颜色转换为 RGB
        if text_color.startswith('#'):
            text_color = text_color[1:]
        
        if len(text_color) == 3:
            r = int(text_color[0] * 2, 16)
            g = int(text_color[1] * 2, 16)
            b = int(text_color[2] * 2, 16)
        elif len(text_color) == 6:
            r = int(text_color[0:2], 16)
            g = int(text_color[2:4], 16)
            b = int(text_color[4:6], 16)
        else:
            return '#e3f2fd'
        
        # 计算浅色背景（降低饱和度和增加亮度）
        # 使用柔和的同色系背景
        r_bg = min(255, int(r * 0.3 + 200))
        g_bg = min(255, int(g * 0.3 + 200))
        b_bg = min(255, int(b * 0.3 + 200))
        
        return f'#{r_bg:02x}{g_bg:02x}{b_bg:02x}'
    
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
    
    def add_todo_item(self):
        """添加待办事项"""
        cursor = self.text_edit.textCursor()
        # 插入待办事项模板
        todo_template = "[ ] 待办事项\n"
        cursor.insertText(todo_template)
        # 移动光标到待办事项文本后面
        cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, len(" 待办事项"))
        self.text_edit.setTextCursor(cursor)
        if not self.is_deleted:
            self.save_note()
    
    def toggle_todo_item(self):
        """切换待办事项状态"""
        cursor = self.text_edit.textCursor()
        # 移动到当前行的开始
        cursor.movePosition(QTextCursor.StartOfLine)
        # 选择行的前3个字符
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 3)
        selected_text = cursor.selectedText()
        
        if selected_text == "[ ]":
            # 标记为已完成
            cursor.insertText("[x]")
        elif selected_text == "[x]":
            # 标记为未完成
            cursor.insertText("[ ]")
        
        if not self.is_deleted:
            self.save_note()
    
    def toggle_code_highlight(self):
        """切换代码高亮"""
        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            # 有选中文本，应用代码高亮样式
            char_format = QTextCharFormat()
            # 设置代码高亮背景色
            char_format.setBackground(QColor('#f5f5f5'))
            # 设置等宽字体
            font = QFont()
            font.setFamily('Courier New')
            char_format.setFont(font)
            # 应用格式
            cursor.mergeCharFormat(char_format)
            if not self.is_deleted:
                self.save_note()
        else:
            # 没有选中文本，提示用户
            QMessageBox.information(self, '提示', '请先选择要高亮的代码文本')
    
    def insert_local_image(self):
        """插入本地图片"""
        # 打开文件选择对话框
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        file_dialog.setNameFilter('Images (*.png *.jpg *.jpeg *.bmp *.gif)')
        
        if file_dialog.exec_() == QFileDialog.Accepted:
            file_path = file_dialog.selectedFiles()[0]
            if os.path.exists(file_path):
                # 插入图片到文本编辑器
                cursor = self.text_edit.textCursor()
                # 插入图片
                cursor.insertImage(file_path)
                if not self.is_deleted:
                    self.save_note()
            else:
                QMessageBox.warning(self, '错误', '所选文件不存在')
    
    def add_local_file_link(self):
        """添加本地文件链接"""
        # 打开文件选择对话框
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        file_dialog.setOption(QFileDialog.DontUseNativeDialog, False)
        
        if file_dialog.exec_() == QFileDialog.Accepted:
            file_path = file_dialog.selectedFiles()[0]
            if os.path.exists(file_path):
                # 获取文件名作为链接文本
                link_text = os.path.basename(file_path)
                # 创建HTML链接
                # 对于本地文件，需要使用file:///协议
                file_url = f"file:///{file_path}"
                html_link = f'<a href="{file_url}">{link_text}</a>'
                
                # 插入链接到文本编辑器
                cursor = self.text_edit.textCursor()
                cursor.insertHtml(html_link)
                if not self.is_deleted:
                    self.save_note()
            else:
                QMessageBox.warning(self, '错误', '所选文件不存在')
    
    def set_reminder(self):
        """设置提醒"""
        dialog = QDialog(self)
        dialog.setWindowTitle('设置提醒')
        dialog.setFixedSize(400, 250)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        
        # 提醒时间
        time_layout = QHBoxLayout()
        time_label = QLabel('提醒时间:')
        self.reminder_time_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.reminder_time_edit.setCalendarPopup(True)
        time_layout.addWidget(time_label)
        time_layout.addWidget(self.reminder_time_edit)
        layout.addLayout(time_layout)
        
        # 重复选项
        repeat_layout = QHBoxLayout()
        repeat_label = QLabel('重复:')
        self.repeat_combo = QComboBox()
        self.repeat_combo.addItems(['不重复', '每天', '每周', '每月'])
        repeat_layout.addWidget(repeat_label)
        repeat_layout.addWidget(self.repeat_combo)
        layout.addLayout(repeat_layout)
        
        # 提醒声音
        sound_layout = QHBoxLayout()
        self.sound_checkbox = QCheckBox('播放提示音')
        self.sound_checkbox.setChecked(True)
        sound_layout.addWidget(self.sound_checkbox)
        layout.addLayout(sound_layout)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        save_btn = QPushButton('保存')
        save_btn.clicked.connect(partial(self.save_reminder, dialog))
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(dialog.close)
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def save_reminder(self, dialog):
        """保存提醒设置"""
        reminder_time = self.reminder_time_edit.dateTime().toString(Qt.ISODate)
        repeat = self.repeat_combo.currentText()
        sound = self.sound_checkbox.isChecked()
        
        # 保存提醒设置
        self.note_data['reminder'] = {
            'time': reminder_time,
            'repeat': repeat,
            'sound': sound
        }
        
        if not self.is_deleted:
            self.save_note()
        
        QMessageBox.information(self, '提醒设置', '提醒已设置')
        dialog.close()
    
    def show_find_replace(self):
        """显示查找和替换对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle('查找和替换')
        dialog.setFixedSize(400, 200)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        
        # 查找输入
        find_layout = QHBoxLayout()
        find_label = QLabel('查找:')
        self.find_edit = QLineEdit()
        find_layout.addWidget(find_label)
        find_layout.addWidget(self.find_edit)
        layout.addLayout(find_layout)
        
        # 替换输入
        replace_layout = QHBoxLayout()
        replace_label = QLabel('替换:')
        self.replace_edit = QLineEdit()
        replace_layout.addWidget(replace_label)
        replace_layout.addWidget(self.replace_edit)
        layout.addLayout(replace_layout)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        find_next_btn = QPushButton('查找下一个')
        find_next_btn.clicked.connect(self.find_next)
        replace_btn = QPushButton('替换')
        replace_btn.clicked.connect(self.replace_current)
        replace_all_btn = QPushButton('全部替换')
        replace_all_btn.clicked.connect(self.replace_all)
        close_btn = QPushButton('关闭')
        close_btn.clicked.connect(dialog.close)
        
        button_layout.addWidget(find_next_btn)
        button_layout.addWidget(replace_btn)
        button_layout.addWidget(replace_all_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def find_next(self):
        """查找下一个匹配项"""
        text = self.find_edit.text()
        if text:
            cursor = self.text_edit.textCursor()
            # 从当前位置开始查找
            found = self.text_edit.find(text, QTextDocument.FindCaseSensitively)
            if not found:
                # 如果没找到，从文档开始查找
                cursor.movePosition(QTextCursor.Start)
                self.text_edit.setTextCursor(cursor)
                found = self.text_edit.find(text, QTextDocument.FindCaseSensitively)
                if not found:
                    QMessageBox.information(self, '查找', '未找到匹配项')
    
    def replace_current(self):
        """替换当前匹配项"""
        text = self.find_edit.text()
        replacement = self.replace_edit.text()
        if text:
            cursor = self.text_edit.textCursor()
            if cursor.hasSelection():
                cursor.insertText(replacement)
                if not self.is_deleted:
                    self.save_note()
                # 查找下一个
                self.find_next()
    
    def replace_all(self):
        """替换所有匹配项"""
        text = self.find_edit.text()
        replacement = self.replace_edit.text()
        if text:
            # 从文档开始
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.text_edit.setTextCursor(cursor)
            
            count = 0
            while self.text_edit.find(text, QTextDocument.FindCaseSensitively):
                cursor = self.text_edit.textCursor()
                cursor.insertText(replacement)
                count += 1
            
            if count > 0:
                QMessageBox.information(self, '替换', f'已替换 {count} 个匹配项')
                if not self.is_deleted:
                    self.save_note()
            else:
                QMessageBox.information(self, '替换', '未找到匹配项')
    
    def toggle_read_mode(self):
        """切换阅读模式"""
        # 检查当前是否处于阅读模式
        if not hasattr(self, 'read_mode'):
            self.read_mode = False
        
        self.read_mode = not self.read_mode
        
        if self.read_mode:
            # 进入阅读模式，隐藏工具栏和其他控件
            self.title_edit.hide()
            self.decrease_font_btn.hide()
            self.increase_font_btn.hide()
            self.separator1.hide()
            self.bold_btn.hide()
            self.italic_btn.hide()
            self.separator2.hide()
            self.color_btn.hide()
            self.tag_btn.hide()
            self.group_btn.hide()
            self.todo_btn.hide()
            self.code_btn.hide()
            self.image_btn.hide()
            self.link_btn.hide()
            self.reminder_btn.hide()
            self.find_btn.hide()
            self.read_mode_btn.hide()
            self.tags_container.hide()
            self.group_container.hide()
            self.transparency_slider.hide()
            self.transparency_label.hide()
            self.topmost_checkbox.hide()
            self.format_checkbox.hide()
            # 找到删除和隐藏按钮所在的布局并隐藏
            for i in range(self.layout().count()):
                item = self.layout().itemAt(i)
                if isinstance(item, QHBoxLayout):
                    # 检查是否是包含删除和隐藏按钮的布局
                    for j in range(item.count()):
                        widget = item.itemAt(j).widget()
                        if widget and isinstance(widget, QPushButton) and (widget.text() == '删除' or widget.text() == '隐藏'):
                            widget.hide()
            # 设置文本编辑器为只读
            self.text_edit.setReadOnly(True)
            # 最大化窗口
            self.showMaximized()
        else:
            # 退出阅读模式，显示所有控件
            self.title_edit.show()
            self.decrease_font_btn.show()
            self.increase_font_btn.show()
            self.separator1.show()
            self.bold_btn.show()
            self.italic_btn.show()
            self.separator2.show()
            self.color_btn.show()
            self.tag_btn.show()
            self.group_btn.show()
            self.todo_btn.show()
            self.code_btn.show()
            self.image_btn.show()
            self.link_btn.show()
            self.reminder_btn.show()
            self.find_btn.show()
            self.read_mode_btn.show()
            self.tags_container.show()
            self.group_container.show()
            self.transparency_slider.show()
            self.transparency_label.show()
            self.topmost_checkbox.show()
            self.format_checkbox.show()
            # 找到删除和隐藏按钮所在的布局并显示
            for i in range(self.layout().count()):
                item = self.layout().itemAt(i)
                if isinstance(item, QHBoxLayout):
                    # 检查是否是包含删除和隐藏按钮的布局
                    for j in range(item.count()):
                        widget = item.itemAt(j).widget()
                        if widget and isinstance(widget, QPushButton) and (widget.text() == '删除' or widget.text() == '隐藏'):
                            widget.show()
            # 设置文本编辑器为可编辑
            self.text_edit.setReadOnly(False)
            # 恢复窗口大小
            self.showNormal()
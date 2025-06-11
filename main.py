import sys
import os
import json
import winreg
from functools import partial
from PyQt5.QtWidgets import (
    QApplication, QWidget, QTextEdit, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QMessageBox, QMenu, QAction,
    QCheckBox, QSystemTrayIcon, QDialog, QFormLayout,
    QLineEdit, QStyle, QColorDialog, QComboBox, QFrame,
    QFontComboBox, QSpinBox, QGroupBox, QTabWidget, QDesktopWidget,
    QSizePolicy, QScrollArea, QGridLayout, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QCoreApplication, QPoint, QRect, QMimeData, QTimer, pyqtSignal, QSize, QThread
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon, QPainter, QPen, QCursor, QGuiApplication, QKeySequence, QPixmap, QTextCursor, QFontDatabase

# 导入新功能模块
from features.search import SearchManager
from features.undo_redo import UndoRedoLineEdit, UndoRedoTextEdit
from features.shortcuts import ShortcutManager
from features.backup import BackupManager
from features.positioning import get_position_manager
from features.formatter import SmartTextEdit, ContentFormatter

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
        self.text_edit.setText(self.note_data.get('content', ''))
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
        separator1 = QLabel('|')
        separator1.setStyleSheet('color: gray; margin: 0 5px;')
        font_layout.addWidget(separator1)
        
        # 加粗按钮
        self.bold_btn = QPushButton('B')
        self.bold_btn.setFixedSize(30, 30)
        self.bold_btn.setCheckable(True)
        self.bold_btn.setToolTip('加粗')
        self.bold_btn.setStyleSheet('''
            QPushButton {
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:checked {
                background-color: #007acc;
                color: white;
                border: 1px solid #005a9e;
            }
        ''')
        self.bold_btn.clicked.connect(self.toggle_bold)
        font_layout.addWidget(self.bold_btn)
        
        # 斜体按钮
        self.italic_btn = QPushButton('I')
        self.italic_btn.setFixedSize(30, 30)
        self.italic_btn.setCheckable(True)
        self.italic_btn.setToolTip('斜体')
        self.italic_btn.setStyleSheet('''
            QPushButton {
                font-style: italic;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:checked {
                background-color: #007acc;
                color: white;
                border: 1px solid #005a9e;
            }
        ''')
        self.italic_btn.clicked.connect(self.toggle_italic)
        font_layout.addWidget(self.italic_btn)
        
        # 添加分隔符
        separator2 = QLabel('|')
        separator2.setStyleSheet('color: gray; margin: 0 5px;')
        font_layout.addWidget(separator2)
        
        # 字体颜色按钮
        self.color_btn = QPushButton('A')
        self.color_btn.setFixedSize(30, 30)
        self.color_btn.setCheckable(True)
        self.color_btn.setToolTip('字体颜色')
        self.color_btn.setStyleSheet('''
            QPushButton {
                color: red;
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:checked {
                background-color: #007acc;
                color: white;
                border: 1px solid #005a9e;
            }
        ''')
        self.color_btn.clicked.connect(self.choose_font_color)
        font_layout.addWidget(self.color_btn)

        font_layout.addStretch()
        main_layout.addLayout(font_layout)

        # 工具栏
        toolbar = QHBoxLayout()

        self.transparency_slider = QSlider(Qt.Horizontal)
        self.transparency_slider.setRange(20, 100)  # 20% 到 100%
        self.transparency_slider.setValue(int(self.note_data.get('opacity', 0.9) * 100))
        self.transparency_slider.setSingleStep(1)
        self.transparency_slider.setFixedWidth(200)  # 增加宽度以适应显示
        self.transparency_slider.valueChanged.connect(self.change_transparency)
        toolbar.addWidget(QLabel('透明度:'))
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

    # ... 余下的 StickyNote 类代码保持不变 ...


    def apply_theme(self):
        # 获取主题CSS文件路径
        theme_css_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'styles', self.theme)
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
                # 如果有其他控件需要单独设置样式，可以在这里处理
                
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
            'opacity': 0.9,
            'always_on_top': True,
            'geometry': None,  # 修改为 None 以便在 initUI 中判断是否需要居中
            'theme': "soft_yellow.css",
            'title_font_size': 12,  # 新增：标题字体大小
            'content_font_size': 12,  # 新增：内容字体大小
            'auto_format_enabled': True  # 新增：自动格式化开关
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
        self.note_data['content'] = self.text_edit.toPlainText()
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
            
            # 直接为每个控件设置样式，使用!important确保优先级
            font_style_sheet = f"""
            font-family: "{font_family}" !important;
            font-size: {font_size}pt !important;
            font-weight: {font_weight} !important;
            font-style: {font_style} !important;
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
    # **新增方法结束**

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
        self.preview_note = QFrame()
        self.preview_note.setFixedSize(280, 200)
        self.preview_note.setFrameStyle(QFrame.StyledPanel)
        
        preview_note_layout = QVBoxLayout()
        
        # 预览标题
        self.preview_title = QLineEdit("预览标题")
        self.preview_title.setReadOnly(True)
        preview_note_layout.addWidget(self.preview_title)
        
        # 预览内容
        self.preview_content = QTextEdit()
        self.preview_content.setPlainText("这是主题预览内容\n可以看到当前主题的样式效果")
        self.preview_content.setReadOnly(True)
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
                self.preview_title.setStyleSheet(css_content)
                self.preview_content.setStyleSheet(css_content)
                self.preview_note.setStyleSheet(css_content)
    
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

class StickyNoteManager:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # 设置应用图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'icon.png')  # 确保存在icon.png
        if not os.path.exists(icon_path):
            # 如果没有自定义图标，使用默认图标
            self.icon = self.app.style().standardIcon(QStyle.SP_DesktopIcon)
        else:
            self.icon = QIcon(icon_path)
        self.app.setWindowIcon(self.icon)

        self.notes = {}
        self.notes_dir = os.path.join(os.getcwd(), 'notes')
        self.notes_dir = os.path.abspath(self.notes_dir)  # 转换为绝对路径
        os.makedirs(self.notes_dir, exist_ok=True)

        # 加载或初始化设置
        self.settings_file = os.path.join(os.getcwd(), 'settings.json')
        self.settings_file = os.path.abspath(self.settings_file)  # 转换为绝对路径
        self.settings = self.load_settings()
        
        # 初始化默认字体设置
        if 'font' not in self.settings:
            self.settings['font'] = {
                'family': '微软雅黑',
                'size': 12,
                'bold': False,
                'italic': False
            }
            self.save_settings()

        # 初始化新功能模块
        self.search_manager = SearchManager(self)
        self.shortcut_manager = ShortcutManager()
        self.backup_manager = BackupManager(self)
        self.position_manager = get_position_manager()
        
        # 注册全局快捷键
        self.setup_global_shortcuts()

        # 设置托盘图标和菜单
        self.setup_tray_icon()

        # 加载已有便签
        self.load_notes()

        # 启动时默认创建一个便签（如果没有）
        if not self.notes:
            self.add_note()

        # 初始化设置对话框实例为空
        self.settings_dialog = None

    def setup_global_shortcuts(self):
        """
        设置全局快捷键
        """
        try:
            # 注册创建新便签的快捷键 (Ctrl+Shift+N)
            self.shortcut_manager.register_global_shortcut(
                'Ctrl+Shift+N', 
                'add_note'
            )
            
            # 注册搜索便签的快捷键 (Ctrl+Shift+F)
            self.shortcut_manager.register_global_shortcut(
                'Ctrl+Shift+F', 
                'show_search_dialog'
            )
            
            # 注册备份管理的快捷键 (Ctrl+Shift+B)
            self.shortcut_manager.register_global_shortcut(
                'Ctrl+Shift+B', 
                'show_backup_dialog'
            )
            
            # 连接快捷键信号到对应方法
            self.shortcut_manager.shortcut_activated.connect(self.handle_shortcut_activated)
            
        except Exception as e:
            print(f"设置全局快捷键时出错: {e}")
    
    def show_search_dialog(self):
        """
        显示搜索对话框
        """
        self.search_manager.show_search_dialog()
    
    def show_backup_dialog(self):
        """
        显示备份管理对话框
        """
        self.backup_manager.show_backup_dialog()
    
    def handle_shortcut_activated(self, action_name):
        """
        处理快捷键激活事件
        
        Args:
            action_name: 动作名称
        """
        try:
            if action_name == 'add_note':
                self.add_note()
            elif action_name == 'show_search_dialog':
                self.show_search_dialog()
            elif action_name == 'show_backup_dialog':
                self.show_backup_dialog()
            else:
                print(f"未知的快捷键动作: {action_name}")
        except Exception as e:
            print(f"处理快捷键激活时出错: {e}")

    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self.icon, parent=self.app)
        self.tray_icon.setToolTip("桌面便签应用")

        self.tray_menu = QMenu()

        # 添加便签
        add_action = QAction("添加便签 (Ctrl+Shift+N)", self.app)
        add_action.triggered.connect(self.add_note)
        self.tray_menu.addAction(add_action)

        # 添加搜索选项
        search_action = QAction("搜索便签 (Ctrl+Shift+F)", self.app)
        search_action.triggered.connect(self.show_search_dialog)
        self.tray_menu.addAction(search_action)

        # 添加备份管理选项
        backup_action = QAction("备份管理 (Ctrl+Shift+B)", self.app)
        backup_action.triggered.connect(self.show_backup_dialog)
        self.tray_menu.addAction(backup_action)

        # 分割线
        self.tray_menu.addSeparator()

        # 创建便签列表的子菜单
        self.notes_menu = QMenu("便签", self.tray_menu)
        self.tray_menu.addMenu(self.notes_menu)

        # 分割线
        self.tray_menu.addSeparator()

        # 开机自启
        self.autostart_action = QAction("开机自启", self.app)
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(self.check_autostart())
        self.autostart_action.triggered.connect(self.toggle_autostart)
        self.tray_menu.addAction(self.autostart_action)

        # 设置
        settings_action = QAction("设置", self.app)
        settings_action.triggered.connect(self.open_settings)
        self.tray_menu.addAction(settings_action)

        # 退出
        exit_action = QAction("退出", self.app)
        exit_action.triggered.connect(self.exit_application)
        self.tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()

        # 双击托盘图标显示一个便签（例如最近打开的便签）
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def update_tray_menu(self):
        # 清空便签子菜单
        self.notes_menu.clear()

        if not self.notes:
            no_notes_action = QAction("暂无便签", self.app)
            no_notes_action.setEnabled(False)
            self.notes_menu.addAction(no_notes_action)
        else:
            for note_id, note in sorted(self.notes.items()):
                note_title = note.note_data.get('title', f'便签 {note_id}')

                # 创建子菜单
                note_menu = QMenu(note_title, self.notes_menu)

                # 添加“打开”选项
                open_action = QAction("打开", self.app)
                open_action.triggered.connect(partial(self.open_note, note_id))  # 使用 partial 绑定 note_id
                note_menu.addAction(open_action)

                # 添加“删除”选项
                delete_action = QAction("删除", self.app)
                delete_action.triggered.connect(partial(self.delete_note, note_id))  # 使用 partial 绑定 note_id
                note_menu.addAction(delete_action)

                # 添加到便签子菜单
                self.notes_menu.addMenu(note_menu)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            # 双击托盘图标打开最近一个便签
            if self.notes:
                # 获取最近打开的便签（假设为 ID 最大的便签）
                last_note_id = max(self.notes.keys())
                self.open_note(last_note_id)

    def add_note(self):
        note_id = self.generate_note_id()
        default_theme_css = self.get_default_theme_css()
        new_note = StickyNote(note_id, self.notes_dir, manager=self, theme_css=default_theme_css)
        new_note.show()
        self.notes[note_id] = new_note
        self.update_tray_menu()

    def open_note(self, note_id):
        if note_id in self.notes:
            note = self.notes[note_id]
            note.show()
            note.raise_()
            note.activateWindow()

    def delete_note(self, note_id):
        if note_id in self.notes:
            note = self.notes[note_id]
            note.delete_note()

    def remove_note(self, note_id):
        if note_id in self.notes:
            del self.notes[note_id]
            self.update_tray_menu()

    def load_notes(self):
        for filename in os.listdir(self.notes_dir):
            if filename.startswith('note_') and filename.endswith('.json'):
                try:
                    note_id_str = filename.split('_')[1].split('.')[0]
                    note_id = int(note_id_str)
                    if note_id in self.notes:
                        continue
                    # 获取主题CSS文件，如果设置了默认主题，使用默认主题
                    default_theme_css = self.get_default_theme_css()
                    new_note = StickyNote(note_id, self.notes_dir, manager=self, theme_css=default_theme_css)
                    new_note.show()
                    self.notes[note_id] = new_note
                except Exception as e:
                    print(f"加载便签时出错: {e}")
        self.update_tray_menu()

    def generate_note_id(self):
        existing_ids = set(self.notes.keys())
        note_id = 1
        while note_id in existing_ids:
            note_id += 1
        return note_id

    def open_settings(self):
        if not self.settings_dialog:
            self.settings_dialog = SettingsDialog(self)
            self.settings_dialog.setWindowModality(Qt.NonModal)  # 设置为非模态对话框
            self.settings_dialog.setAttribute(Qt.WA_DeleteOnClose, True)
            self.settings_dialog.destroyed.connect(self.on_settings_closed)
            self.settings_dialog.show()
        else:
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()

    def on_settings_closed(self):
        self.settings_dialog = None

    def set_autostart(self, enable=True):
        exe_path = os.path.realpath(sys.argv[0])
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, run_key, 0, winreg.KEY_SET_VALUE)
            if enable:
                winreg.SetValueEx(key, "StickyNoteApp", 0, winreg.REG_SZ, exe_path)
            else:
                try:
                    winreg.DeleteValue(key, "StickyNoteApp")
                except FileNotFoundError:
                    pass  # 如果不存在则忽略
            winreg.CloseKey(key)
            return True
        except Exception as e:
            QMessageBox.warning(None, '设置开机自启失败', f'无法设置开机自启: {e}')
            return False

    def check_autostart(self):
        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, run_key, 0, winreg.KEY_READ)
            value, regtype = winreg.QueryValueEx(key, "StickyNoteApp")
            winreg.CloseKey(key)
            return True if value else False
        except FileNotFoundError:
            return False
        except Exception as e:
            QMessageBox.warning(None, '检查开机自启失败', f'无法检查开机自启状态: {e}')
            return False

    def toggle_autostart(self, checked):
        if checked:
            success = self.set_autostart(True)
            if success:
                QMessageBox.information(None, '开机自启', '已启用开机自启。')
            else:
                self.autostart_action.setChecked(False)
        else:
            success = self.set_autostart(False)
            if success:
                QMessageBox.information(None, '开机自启', '已禁用开机自启。')
            else:
                self.autostart_action.setChecked(True)

    def exit_application(self):
        # 清理快捷键
        try:
            self.shortcut_manager.cleanup()
        except Exception as e:
            print(f"清理快捷键时出错: {e}")
        
        for note in list(self.notes.values()):
            note.close()
        self.tray_icon.hide()
        QCoreApplication.quit()

    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                QMessageBox.warning(None, '加载设置错误', f'无法加载设置文件: {e}')
                return {
                    'default_theme': "soft_yellow.css"
                }
        else:
            return {
                'default_theme': "soft_yellow.css"
            }

    def save_settings(self):
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            QMessageBox.warning(None, '保存设置错误', f'无法保存设置文件: {e}')

    def get_available_themes(self):
        """
        扫描 styles 文件夹，读取每个 CSS 文件的主题名称，并返回一个字典
        """
        themes = {}
        styles_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'styles')
        if not os.path.exists(styles_dir):
            os.makedirs(styles_dir, exist_ok=True)

        for filename in os.listdir(styles_dir):
            if filename.endswith('.css'):
                filepath = os.path.join(styles_dir, filename)
                theme_name = self.extract_theme_name_from_css(filepath)
                if theme_name:
                    themes[theme_name] = filename
        return themes

    def extract_theme_name_from_css(self, filepath):
        """
        从 CSS 文件中提取主题名称。假设主题名称在文件的第一行，如：
        /* Theme Name: 柔和黄色 */
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('/*') and 'Theme Name:' in line:
                        # 提取主题名称
                        start = line.find('Theme Name:') + len('Theme Name:')
                        end = line.find('*/', start)
                        if end == -1:
                            end = len(line)
                        theme_name = line[start:end].strip()
                        return theme_name
                    elif line and not line.startswith('/*'):
                        # 第一行不是主题名称注释，跳过
                        break
            return None
        except Exception as e:
            print(f"无法从 {filepath} 中提取主题名称: {e}")
            return None

    def get_theme_name_by_css(self, css_filename):
        """
        根据 CSS 文件名返回主题名称
        """
        for name, filename in self.get_available_themes().items():
            if filename == css_filename:
                return name
        return None

    def get_default_theme_css(self):
        return self.settings.get('default_theme', "soft_yellow.css")

    def set_default_theme(self, theme_css):
        self.settings['default_theme'] = theme_css
        self.save_settings()

    def apply_theme_to_all_notes(self):
        for note in self.notes.values():
            note.set_theme(self.get_default_theme_css())
    
    def get_default_font(self):
        """获取默认字体设置"""
        return self.settings.get('font', {
            'family': '微软雅黑',
            'size': 12,
            'bold': False,
            'italic': False
        })
    
    def set_default_font(self, font_settings):
        """设置默认字体"""
        self.settings['font'] = font_settings
        self.save_settings()
    
    def apply_font_to_all_notes(self):
        """应用字体设置到所有便签"""
        font_settings = self.get_default_font()
        for note in self.notes.values():
            note.set_font(font_settings)

    def run(self):
        sys.exit(self.app.exec_())

def main():
        manager = StickyNoteManager()
        manager.run()

if __name__ == '__main__':
    main()

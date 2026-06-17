# -*- coding: utf-8 -*-
"""
便签核心模块

包含便签窗口组件 (StickyNote) 和基础编辑器控件 (PlainLineEdit, PlainTextEdit)，
以及异步保存工作线程 (NoteSaveWorker)。
"""

import os
import json
import logging
import re
import time
import copy

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QMessageBox, QCheckBox,
    QColorDialog, QSystemTrayIcon, QMenu, QAction,
    QStackedWidget, QTextBrowser, QTextEdit, QInputDialog, QFileDialog,
    QListWidget, QDialog, QLineEdit
)
from PyQt5.QtCore import Qt, QPoint, QRect, QMimeData, QTimer, QThread, QSize, QPropertyAnimation, QEasingCurve, QEvent, pyqtSignal
from PyQt5.QtGui import (
    QFont, QColor, QPalette, QCursor, QPainter, QPen, QTextCharFormat
)

from features.undo_redo import UndoRedoLineEdit, UndoRedoTextEdit, UndoRedoManager
from features.positioning import get_position_manager
from features.formatter import ContentFormatter
from features.tag import TagChipWidget
from features.richtext import RichTextActions
from core import get_styles_dir, __version__

# 窗口调整大小检测边界宽度
RESIZE_MARGIN = 10

# 窗口吸附阈值 (像素)
SNAP_THRESHOLD = 15

# 保存防抖延迟 (毫秒)
SAVE_DEBOUNCE_MS = 500


class NoteSaveWorker(QThread):
    """
    便签异步保存工作线程

    在后台执行 JSON 序列化和文件写入，避免阻塞 UI 主线程。
    """
    save_completed = None  # 保留备用信号
    save_failed = None

    def __init__(self, note_data: dict, file_path: str):
        super().__init__()
        self.note_data = note_data
        self.file_path = file_path

    def run(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self.note_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[NoteSaveWorker] 保存失败: {self.file_path} - {e}")


class NoteLoadWorker(QThread):
    """
    便签异步加载工作线程

    在后台线程读取并解析 JSON 文件，通过信号返回结果。
    避免启动时大量 I/O 阻塞 UI。
    """
    loaded = pyqtSignal(int, dict)  # (note_id, note_data)
    failed = pyqtSignal(int, str)   # (note_id, error_message)

    def __init__(self, note_id: int, file_path: str):
        super().__init__()
        self.note_id = note_id
        self.file_path = file_path

    def run(self):
        try:
            if not os.path.exists(self.file_path):
                self.failed.emit(self.note_id, '文件不存在')
                return
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.loaded.emit(self.note_id, data)
        except Exception as e:
            self.failed.emit(self.note_id, str(e))


class PlainLineEdit(UndoRedoLineEdit):
    """纯文本标题编辑器 — 粘贴时去除富文本格式"""

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
    """纯文本内容编辑器 — 可选智能格式化粘贴"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.formatter = ContentFormatter()
        self.auto_format_enabled = True

    def set_auto_format_enabled(self, enabled: bool):
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
    """
    便签窗口

    无边框窗口，支持拖拽、边缘调整大小、富文本编辑、
    主题切换、字体设置、透明度调节和防抖异步保存。
    """

    def __init__(self, note_id, notes_dir='notes', manager=None, theme_css="soft_yellow.css", preloaded_data=None):
        super().__init__()
        self.note_id = note_id
        self.manager = manager
        self.is_deleted = False

        self.notes_dir = os.path.realpath(os.path.abspath(notes_dir))
        os.makedirs(self.notes_dir, exist_ok=True)
        self.note_file = os.path.join(self.notes_dir, f'note_{self.note_id}.json')
        # 路径穿越防护：确保 note_file 在 notes_dir 内
        real_note_file = os.path.realpath(self.note_file)
        if not real_note_file.startswith(self.notes_dir + os.sep):
            raise ValueError(f'便签文件路径不合法: {self.note_file}')
        self.note_data = self.load_note(preloaded_data)

        self.theme = self.note_data.get('theme', theme_css)

        self.dragging = False
        self.resizing = False
        self.resize_dir = None
        self.offset = QPoint()

        # 防抖保存定时器
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_save_to_disk)

        # 活跃的保存线程引用，防止被 GC 回收
        self._save_worker = None

        # 贴边自动隐藏状态
        self.auto_hidden = False          # 是否处于自动隐藏状态
        self.hidden_edge = None           # 隐藏的边缘: 'left' / 'right' / 'top' / 'bottom'
        self._pre_hide_geometry = None    # 隐藏前的窗口位置和大小
        self.hide_tab = None              # 隐藏后显示的标签页小窗口
        self._hover_restored = False      # 当前展开是否由悬停触发（离开即缩回）
        self._auto_rehide_timer = None    # 悬停展开后自动缩回的延迟定时器

        # 锁定/置顶/收藏状态
        self.is_locked = self.note_data.get('locked', False)
        self.is_pinned = self.note_data.get('pinned', False)
        self.is_favorite = self.note_data.get('favorite', False)

        # paintEvent 渲染缓存
        self._border_pen = QPen(QColor(200, 200, 200))
        self._border_pen.setWidth(2)

        # 屏幕几何缓存
        self._screen_geo_cache = None
        self._screen_geo_cache_time = 0

        self.initUI()

    def initUI(self):
        self.setWindowTitle(self.note_data.get('title', f'\u4fbf\u7b7e {self.note_id}'))
        flags = Qt.Window | Qt.FramelessWindowHint
        if self.note_data.get('always_on_top', True):
            flags |= Qt.WindowStaysOnTopHint
        flags |= Qt.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_NoSystemBackground, False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        # 启用鼠标追踪，以便悬停在边缘时自动切换为缩放光标
        self.setMouseTracking(True)

        # 主布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN)

        # 标题编辑
        self.title_edit = PlainLineEdit()
        self.title_edit.setFixedHeight(40)
        self.title_edit.setText(self.note_data.get('title', f'\u4fbf\u7b7e {self.note_id}'))
        self.title_edit.textChanged.connect(self.update_title)
        self.title_edit.setMaxLength(50)
        main_layout.addWidget(self.title_edit)

        # 内容编辑
        self.text_edit = PlainTextEdit()
        content = self.note_data.get('content', '')
        if content and (content.startswith('<!DOCTYPE') or '<html>' in content):
            self.text_edit.setHtml(content)
        else:
            self.text_edit.setText(content)
        self.text_edit.textChanged.connect(self.update_content)

        # Rich text actions 封装
        self.rich_text = RichTextActions(self.text_edit)
        self.is_markdown_mode = False
        self.md_renderer = None

        # 编辑器栈（富文本编辑 / Markdown 预览）
        self.editor_stack = QStackedWidget()
        self.editor_stack.addWidget(self.text_edit)  # page 0: 富文本编辑器
        self.md_preview = QTextBrowser()
        self.md_preview.setOpenExternalLinks(True)
        # 设置独立样式，防止被便签主题样式覆盖列表标号
        self.md_preview.setStyleSheet('''
            QTextBrowser {
                background-color: #FFFFFF;
                border: 1px solid #ddd;
            }
        ''')
        self.editor_stack.addWidget(self.md_preview)  # page 1: Markdown 预览
        main_layout.addWidget(self.editor_stack)

        # 撤销/重做管理器
        self.undo_redo_manager = UndoRedoManager(self.title_edit, self.text_edit)
        self.title_edit.set_undo_redo_manager(self.undo_redo_manager)
        self.text_edit.set_undo_redo_manager(self.undo_redo_manager)
        self.undo_redo_manager.state_changed.connect(self._update_undo_redo_buttons)

        # 字体大小调整按钮布局
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

        self.separator1 = QLabel('|')
        font_layout.addWidget(self.separator1)

        # 加粗按钮
        self.bold_btn = QPushButton('B')
        self.bold_btn.setFixedSize(30, 30)
        self.bold_btn.setCheckable(True)
        self.bold_btn.setToolTip('\u52a0\u7c97')
        self.bold_btn.clicked.connect(self.toggle_bold)
        font_layout.addWidget(self.bold_btn)

        # 斜体按钮
        self.italic_btn = QPushButton('I')
        self.italic_btn.setFixedSize(30, 30)
        self.italic_btn.setCheckable(True)
        self.italic_btn.setToolTip('\u659c\u4f53')
        self.italic_btn.clicked.connect(self.toggle_italic)
        font_layout.addWidget(self.italic_btn)

        self.separator2 = QLabel('|')
        font_layout.addWidget(self.separator2)

        # 字体颜色按钮
        self.color_btn = QPushButton('A')
        self.color_btn.setFixedSize(30, 30)
        self.color_btn.setCheckable(True)
        self.color_btn.setToolTip('\u5b57\u4f53\u989c\u8272')
        self.color_btn.clicked.connect(self.choose_font_color)
        font_layout.addWidget(self.color_btn)

        # 下划线
        self.separator3 = QLabel('|')
        font_layout.addWidget(self.separator3)

        self.underline_btn = QPushButton('U')
        self.underline_btn.setFixedSize(30, 30)
        self.underline_btn.setCheckable(True)
        self.underline_btn.setToolTip('下划线')
        self.underline_btn.clicked.connect(self._toggle_underline)
        font_layout.addWidget(self.underline_btn)

        # 删除线
        self.strikethrough_btn = QPushButton('S')
        self.strikethrough_btn.setFixedSize(30, 30)
        self.strikethrough_btn.setCheckable(True)
        self.strikethrough_btn.setToolTip('删除线')
        self.strikethrough_btn.clicked.connect(self._toggle_strikethrough)
        font_layout.addWidget(self.strikethrough_btn)

        # 上标/下标
        self.separator4 = QLabel('|')
        font_layout.addWidget(self.separator4)

        self.superscript_btn = QPushButton('x²')
        self.superscript_btn.setFixedSize(30, 30)
        self.superscript_btn.setToolTip('上标')
        self.superscript_btn.clicked.connect(self.rich_text.toggle_superscript)
        font_layout.addWidget(self.superscript_btn)

        self.subscript_btn = QPushButton('x₂')
        self.subscript_btn.setFixedSize(30, 30)
        self.subscript_btn.setToolTip('下标')
        self.subscript_btn.clicked.connect(self.rich_text.toggle_subscript)
        font_layout.addWidget(self.subscript_btn)

        # 对齐
        self.separator5 = QLabel('|')
        font_layout.addWidget(self.separator5)

        self.align_left_btn = QPushButton('⇤')
        self.align_left_btn.setFixedSize(30, 30)
        self.align_left_btn.setToolTip('左对齐')
        self.align_left_btn.clicked.connect(lambda: self.rich_text.set_alignment(Qt.AlignLeft))
        font_layout.addWidget(self.align_left_btn)

        self.align_center_btn = QPushButton('≡')
        self.align_center_btn.setFixedSize(30, 30)
        self.align_center_btn.setToolTip('居中')
        self.align_center_btn.clicked.connect(lambda: self.rich_text.set_alignment(Qt.AlignCenter))
        font_layout.addWidget(self.align_center_btn)

        self.align_right_btn = QPushButton('⇥')
        self.align_right_btn.setFixedSize(30, 30)
        self.align_right_btn.setToolTip('右对齐')
        self.align_right_btn.clicked.connect(lambda: self.rich_text.set_alignment(Qt.AlignRight))
        font_layout.addWidget(self.align_right_btn)

        # 列表
        self.separator6 = QLabel('|')
        font_layout.addWidget(self.separator6)

        self.ordered_list_btn = QPushButton('1.')
        self.ordered_list_btn.setFixedSize(30, 30)
        self.ordered_list_btn.setToolTip('有序列表')
        self.ordered_list_btn.clicked.connect(self.rich_text.insert_ordered_list)
        font_layout.addWidget(self.ordered_list_btn)

        self.unordered_list_btn = QPushButton('•')
        self.unordered_list_btn.setFixedSize(30, 30)
        self.unordered_list_btn.setToolTip('无序列表')
        self.unordered_list_btn.clicked.connect(self.rich_text.insert_unordered_list)
        font_layout.addWidget(self.unordered_list_btn)

        # 高亮
        self.separator7 = QLabel('|')
        font_layout.addWidget(self.separator7)

        self.highlight_btn = QPushButton('🖍')
        self.highlight_btn.setFixedSize(30, 30)
        self.highlight_btn.setToolTip('背景高亮')
        self.highlight_btn.clicked.connect(self._choose_highlight_color)
        font_layout.addWidget(self.highlight_btn)

        self.clear_highlight_btn = QPushButton('✖')
        self.clear_highlight_btn.setFixedSize(30, 30)
        self.clear_highlight_btn.setToolTip('清除高亮')
        self.clear_highlight_btn.clicked.connect(self.rich_text.clear_highlight)
        font_layout.addWidget(self.clear_highlight_btn)

        font_layout.addStretch()
        main_layout.addLayout(font_layout)

        # 工具栏
        toolbar = QHBoxLayout()

        self.transparency_slider = QSlider(Qt.Horizontal)
        self.transparency_slider.setRange(20, 100)
        self.transparency_slider.setValue(int(self.note_data.get('opacity', 0.9) * 100))
        self.transparency_slider.setSingleStep(1)
        self.transparency_slider.setFixedWidth(200)
        self.transparency_slider.valueChanged.connect(self.change_transparency)
        self.transparency_label = QLabel('\u900f\u660e\u5ea6:')
        toolbar.addWidget(self.transparency_label)
        toolbar.addWidget(self.transparency_slider)

        self.topmost_checkbox = QCheckBox("\u603b\u5728\u6700\u524d")
        self.topmost_checkbox.setChecked(self.note_data.get('always_on_top', True))
        self.topmost_checkbox.stateChanged.connect(self.toggle_always_on_top)
        toolbar.addWidget(self.topmost_checkbox)

        self.format_checkbox = QCheckBox("\u667a\u80fd\u683c\u5f0f\u5316")
        self.format_checkbox.setChecked(self.note_data.get('auto_format_enabled', True))
        self.format_checkbox.setToolTip('\u542f\u7528\u540e\u7c98\u8d34\u65f6\u81ea\u52a8\u683c\u5f0f\u5316')
        self.format_checkbox.stateChanged.connect(self.toggle_auto_format)
        toolbar.addWidget(self.format_checkbox)

        toolbar.addStretch()

        # 按钮布局
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        
        # 撤销/重做按钮
        self.undo_btn = QPushButton('↩')
        self.undo_btn.setToolTip('撤销 (Ctrl+Z)')
        self.undo_btn.setFixedSize(36, 30)
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.undo_redo_manager.undo)
        buttons_layout.addWidget(self.undo_btn)

        self.redo_btn = QPushButton('↪')
        self.redo_btn.setToolTip('重做 (Ctrl+Y)')
        self.redo_btn.setFixedSize(36, 30)
        self.redo_btn.setEnabled(False)
        self.redo_btn.clicked.connect(self.undo_redo_manager.redo)
        buttons_layout.addWidget(self.redo_btn)

        # 标签按钮
        self.tag_btn = QPushButton('🏷')
        self.tag_btn.setToolTip('设置标签')
        self.tag_btn.setFixedSize(36, 30)
        self.tag_btn.clicked.connect(self.open_tag_selector)
        buttons_layout.addWidget(self.tag_btn)
        
        # 提醒按钮
        self.reminder_btn = QPushButton('⏰')
        self.reminder_btn.setToolTip('设置提醒')
        self.reminder_btn.setFixedSize(36, 30)
        self.reminder_btn.clicked.connect(self.open_reminder_dialog)
        buttons_layout.addWidget(self.reminder_btn)
        
        # 锁定/解锁按钮
        self.lock_btn = QPushButton('🔒' if self.is_locked else '🔓')
        self.lock_btn.setToolTip('锁定便签' if not self.is_locked else '解锁便签')
        self.lock_btn.setFixedSize(36, 30)
        self.lock_btn.clicked.connect(self._toggle_lock)
        buttons_layout.addWidget(self.lock_btn)
        
        # 插入链接
        self.link_btn = QPushButton('🔗')
        self.link_btn.setToolTip('插入链接')
        self.link_btn.setFixedSize(36, 30)
        self.link_btn.clicked.connect(self._insert_hyperlink_dialog)
        buttons_layout.addWidget(self.link_btn)
        
        # 插入图片
        self.image_btn = QPushButton('🖼')
        self.image_btn.setToolTip('插入图片')
        self.image_btn.setFixedSize(36, 30)
        self.image_btn.clicked.connect(self._insert_image_dialog)
        buttons_layout.addWidget(self.image_btn)
        
        # Markdown 预览切换
        self.md_toggle_btn = QPushButton('MD')
        self.md_toggle_btn.setToolTip('切换 Markdown 预览')
        self.md_toggle_btn.setFixedSize(36, 30)
        self.md_toggle_btn.setCheckable(True)
        self.md_toggle_btn.clicked.connect(self._toggle_markdown_mode)
        buttons_layout.addWidget(self.md_toggle_btn)
        
        # 便签反向链接
        self.backlink_btn = QPushButton('🔙')
        self.backlink_btn.setToolTip('便签反向链接')
        self.backlink_btn.setFixedSize(36, 30)
        self.backlink_btn.clicked.connect(self._show_backlinks)
        buttons_layout.addWidget(self.backlink_btn)
        
        self.delete_btn = QPushButton('删除')
        self.delete_btn.setToolTip('\u5220\u9664\u4fbf\u7b7e')
        self.delete_btn.setFixedSize(60, 30)
        self.delete_btn.clicked.connect(self.delete_note)
        buttons_layout.addWidget(self.delete_btn)
        
        # 使用说明按钮
        self.help_btn = QPushButton('?')
        self.help_btn.setToolTip('使用说明 — 选中文字后可调整大小/颜色/加粗/斜体')
        self.help_btn.setFixedSize(30, 30)
        self.help_btn.clicked.connect(self.show_quick_help)
        buttons_layout.addWidget(self.help_btn)
        
        self.hide_btn = QPushButton('隐藏')
        self.hide_btn.setToolTip('\u9690\u85cf\u4fbf\u7b7e')
        self.hide_btn.setFixedSize(60, 30)
        self.hide_btn.clicked.connect(self.hide_note)
        buttons_layout.addWidget(self.hide_btn)

        toolbar.addLayout(buttons_layout)
        main_layout.addLayout(toolbar)

        # 标签芯片显示区（版本号固定左下角，标签在其右侧排列）
        self.tags_layout = QHBoxLayout()
        self.tags_layout.setContentsMargins(0, 2, 0, 2)
        self.tags_layout.setSpacing(4)

        # 版本标签（固定在最左侧）
        self.version_label = QLabel(f'v{__version__}')
        self.version_label.setStyleSheet('color: #bbb; font-size: 7pt; background: transparent; border: none;')
        self.version_label.setToolTip(f'StickyNote v{__version__} by MaWenshui')
        self.tags_layout.addWidget(self.version_label)

        # 标签芯片将插入到这里（版本号右侧）
        self.tags_layout.addStretch()  # stretch 在最后，将标签靠左排列

        main_layout.addLayout(self.tags_layout)

        self.setLayout(main_layout)

        self.apply_theme()

        # 应用字体设置
        if self.manager:
            saved_font_settings = self.note_data.get('font_settings')
            if saved_font_settings:
                self.set_font(saved_font_settings)
            else:
                font_settings = self.manager.get_default_font()
                self.set_font(font_settings)

        self.title_font_size = self.note_data.get('title_font_size', 12)
        self.content_font_size = self.note_data.get('content_font_size', 12)
        self.set_font_size(self.title_font_size, self.content_font_size)

        if hasattr(self, 'font_settings') and self.font_settings:
            self.bold_btn.setChecked(self.font_settings.get('bold', False))
            self.italic_btn.setChecked(self.font_settings.get('italic', False))

        if 'font_color' in self.note_data:
            self.font_color = self.note_data['font_color']
            if self.font_color != '#000000':
                self.color_btn.setChecked(True)
        else:
            self.font_color = '#000000'

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

        auto_format_enabled = self.note_data.get('auto_format_enabled', True)
        self.text_edit.set_auto_format_enabled(auto_format_enabled)

        self.setWindowOpacity(self.note_data.get('opacity', 0.9))

        # 设置窗口位置和大小
        saved_geometry = self.note_data.get('geometry')
        position_manager = get_position_manager()
        if saved_geometry:
            self.setGeometry(QRect(
                saved_geometry.get('x', 100),
                saved_geometry.get('y', 100),
                saved_geometry.get('width', 400),
                saved_geometry.get('height', 300)
            ))
            position_manager.register_window_position(
                self.note_id,
                QPoint(saved_geometry.get('x', 100), saved_geometry.get('y', 100)),
                QSize(saved_geometry.get('width', 400), saved_geometry.get('height', 300))
            )
        else:
            smart_position = position_manager.get_smart_position(self.note_id)
            self.resize(400, 300)
            self.move(smart_position)
            position_manager.register_window_position(
                self.note_id, smart_position, QSize(400, 300)
            )

        # 更新提醒按钮显示
        self.update_reminder_display()

        # 刷新标签芯片
        self.refresh_tag_chips()

    # ==================== 字体和样式 ====================

    def set_font_size(self, title_size, content_size):
        title_font = QFont()
        title_font.setPointSize(title_size)
        title_font.setBold(True)
        self.title_edit.setFont(title_font)
        content_font = QFont()
        content_font.setPointSize(content_size)
        self.text_edit.setFont(content_font)

    def _change_selected_font_size(self, delta):
        """修改选中文字的字体大小（仅影响 text_edit 中的选中文本）"""
        cursor = self.text_edit.textCursor()
        if not cursor.hasSelection():
            return False
        fmt = cursor.charFormat()
        current_size = fmt.fontPointSize()
        if current_size <= 0:
            current_size = self.text_edit.font().pointSize() or 12
        new_size = max(6, current_size + delta)
        fmt.setFontPointSize(new_size)
        cursor.mergeCharFormat(fmt)
        return True

    def increase_font_size(self):
        # 如果有选中文本，只改变选中文本的字体大小
        if self.text_edit.textCursor().hasSelection():
            self._change_selected_font_size(1)
            if not self.is_deleted:
                self.save_note()
            return
        # 无选中文本时，只改变内容编辑器的字体大小（不影响标题）
        if hasattr(self, 'font_settings') and self.font_settings:
            current_size = self.font_settings.get('size', 12)
            self.font_settings['size'] = current_size + 1
            self._apply_font_to_content_only()
            if not self.is_deleted:
                self.save_note()
        else:
            self.content_font_size += 1
            content_font = QFont()
            content_font.setPointSize(self.content_font_size)
            self.text_edit.setFont(content_font)
            self.note_data['content_font_size'] = self.content_font_size
            if not self.is_deleted:
                self.save_note()

    def decrease_font_size(self):
        # 如果有选中文本，只改变选中文本的字体大小
        if self.text_edit.textCursor().hasSelection():
            self._change_selected_font_size(-1)
            if not self.is_deleted:
                self.save_note()
            return
        # 无选中文本时，只改变内容编辑器的字体大小（不影响标题）
        if hasattr(self, 'font_settings') and self.font_settings:
            current_size = self.font_settings.get('size', 12)
            if current_size > 6:
                self.font_settings['size'] = current_size - 1
                self._apply_font_to_content_only()
                if not self.is_deleted:
                    self.save_note()
        else:
            if self.content_font_size > 6:
                self.content_font_size -= 1
            content_font = QFont()
            content_font.setPointSize(self.content_font_size)
            self.text_edit.setFont(content_font)
            self.note_data['content_font_size'] = self.content_font_size
            if not self.is_deleted:
                self.save_note()

    def _apply_font_to_content_only(self):
        """仅将字体设置应用到内容编辑器，不影响标题"""
        font_settings = getattr(self, 'font_settings', {})
        if not font_settings:
            return
        font_family = font_settings.get('family', '微软雅黑')
        font_size = font_settings.get('size', 12)
        font_weight = 'bold' if font_settings.get('bold', False) else 'normal'
        font_style = 'italic' if font_settings.get('italic', False) else 'normal'
        font_color = getattr(self, 'font_color', '#000000')
        font_style_sheet = f'''
            font-family: "{font_family}" !important;
            font-size: {font_size}pt !important;
            font-weight: {font_weight} !important;
            font-style: {font_style} !important;
            color: {font_color} !important;
        '''
        self.text_edit.setStyleSheet(self.text_edit.styleSheet() + font_style_sheet)

    def toggle_bold(self):
        current_editor = self._get_focused_editor()
        cursor = current_editor.textCursor()
        if cursor.hasSelection():
            char_format = cursor.charFormat()
            current_bold = char_format.fontWeight() == QFont.Bold
            char_format.setFontWeight(QFont.Normal if current_bold else QFont.Bold)
            cursor.mergeCharFormat(char_format)
            self.bold_btn.setChecked(not current_bold)
        else:
            char_format = current_editor.currentCharFormat()
            current_bold = char_format.fontWeight() == QFont.Bold
            char_format.setFontWeight(QFont.Normal if current_bold else QFont.Bold)
            current_editor.setCurrentCharFormat(char_format)
            self.bold_btn.setChecked(not current_bold)
        if hasattr(self, 'font_settings') and self.font_settings:
            self.font_settings['bold'] = self.bold_btn.isChecked()
            if not self.is_deleted:
                self.save_note()

    def toggle_italic(self):
        current_editor = self._get_focused_editor()
        cursor = current_editor.textCursor()
        if cursor.hasSelection():
            char_format = cursor.charFormat()
            current_italic = char_format.fontItalic()
            char_format.setFontItalic(not current_italic)
            cursor.mergeCharFormat(char_format)
            self.italic_btn.setChecked(not current_italic)
        else:
            char_format = current_editor.currentCharFormat()
            current_italic = char_format.fontItalic()
            char_format.setFontItalic(not current_italic)
            current_editor.setCurrentCharFormat(char_format)
            self.italic_btn.setChecked(not current_italic)
        if hasattr(self, 'font_settings') and self.font_settings:
            self.font_settings['italic'] = self.italic_btn.isChecked()
            if not self.is_deleted:
                self.save_note()

    def choose_font_color(self):
        current_color = getattr(self, 'font_color', '#000000')
        color = QColorDialog.getColor(QColor(current_color), self, '\u9009\u62e9\u5b57\u4f53\u989c\u8272')
        if not color.isValid():
            return
        color_hex = color.name()
        self.font_color = color_hex
        self.color_btn.setChecked(True)
        self.color_btn.setStyleSheet(f'''
            QPushButton {{
                color: {color_hex}; font-weight: bold;
                border: 1px solid #ccc; border-radius: 3px;
            }}
            QPushButton:checked {{
                background-color: #007acc; color: white;
                border: 1px solid #005a9e;
            }}
        ''')
        current_editor = self._get_focused_editor()
        cursor = current_editor.textCursor()
        if cursor.hasSelection():
            char_format = cursor.charFormat()
            char_format.setForeground(QColor(color_hex))
            cursor.mergeCharFormat(char_format)
        else:
            char_format = current_editor.currentCharFormat()
            char_format.setForeground(QColor(color_hex))
            current_editor.setCurrentCharFormat(char_format)
        self.note_data['font_color'] = color_hex
        if not self.is_deleted:
            self.save_note()

    def _get_focused_editor(self):
        if self.text_edit.hasFocus():
            return self.text_edit
        elif self.title_edit.hasFocus():
            return self.title_edit
        return self.text_edit

    def is_dark_theme(self, theme_css_content):
        """检测主题是否为深色主题（基于背景色 W3C 相对亮度）"""
        bg_match = re.search(r'StickyNote\s*{[^}]*background-color:\s*([^;]+);', theme_css_content)
        if bg_match:
            bg_color = bg_match.group(1).strip()
            hex_match = re.match(r'#([0-9a-fA-F]{3,8})', bg_color)
            if hex_match:
                hex_str = hex_match.group(1)
                if len(hex_str) == 3:
                    r, g, b = int(hex_str[0]*2, 16), int(hex_str[1]*2, 16), int(hex_str[2]*2, 16)
                elif len(hex_str) >= 6:
                    r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
                else:
                    return False
                luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
                return luminance < 0.5
            dark_keywords = ['#2', '#3', '#4', '#5', 'black', 'dark']
            return any(keyword in bg_color.lower() for keyword in dark_keywords)
        return False

    def get_adaptive_control_styles(self, is_dark):
        if is_dark:
            return {
                'separator_color': '#CCCCCC', 'bg': '#555555',
                'color': '#FFFFFF', 'border': '#777777',
                'hover_bg': '#666666', 'checked_bg': '#007acc',
                'checked_color': '#FFFFFF'
            }
        else:
            return {
                'separator_color': '#666666', 'bg': '#F0F0F0',
                'color': '#000000', 'border': '#CCCCCC',
                'hover_bg': '#E0E0E0', 'checked_bg': '#007acc',
                'checked_color': '#FFFFFF'
            }

    def apply_adaptive_control_styles(self, styles):
        # 分隔符标签样式
        for sep in ['separator1', 'separator2', 'separator3', 'separator4',
                     'separator5', 'separator6', 'separator7']:
            if hasattr(self, sep):
                getattr(self, sep).setStyleSheet(f'color: {styles["separator_color"]}; margin: 0 5px;')
        if hasattr(self, 'transparency_label'):
            self.transparency_label.setStyleSheet(f'color: {styles["separator_color"]}; margin: 0 5px;')

        # 通用按钮模板
        button_template = '''
            QPushButton {{
                background-color: {bg}; color: {color}; border: 1px solid {border};
                border-radius: 3px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {hover_bg}; }}
            QPushButton:checked {{ background-color: {checked_bg}; color: {checked_color}; border: 1px solid {checked_bg}; }}
            QPushButton:disabled {{ color: #888; background-color: #444; }}
        '''
        base_style = button_template.format(**styles)

        # 字体工具栏按钮
        for btn in ['decrease_font_btn', 'increase_font_btn', 'bold_btn',
                     'underline_btn', 'strikethrough_btn', 'superscript_btn',
                     'subscript_btn', 'align_left_btn', 'align_center_btn',
                     'align_right_btn', 'ordered_list_btn', 'unordered_list_btn',
                     'highlight_btn', 'clear_highlight_btn']:
            if hasattr(self, btn):
                getattr(self, btn).setStyleSheet(base_style)

        # 斜体按钮（加 italic 样式）
        if hasattr(self, 'italic_btn'):
            italic_style = button_template.replace('font-weight: bold;', 'font-weight: bold; font-style: italic;').format(**styles)
            self.italic_btn.setStyleSheet(italic_style)

        # 颜色按钮（红色文字）
        if hasattr(self, 'color_btn'):
            color_style = button_template.replace('color: {color}', 'color: red').format(**styles)
            self.color_btn.setStyleSheet(color_style)

        # 功能按钮（撤销/重做/标签/提醒/锁定/链接/图片/MD/反链/删除/帮助/隐藏）
        for btn in ['undo_btn', 'redo_btn', 'tag_btn', 'reminder_btn',
                     'lock_btn', 'link_btn', 'image_btn', 'md_toggle_btn',
                     'backlink_btn', 'help_btn', 'hide_btn']:
            if hasattr(self, btn):
                getattr(self, btn).setStyleSheet(base_style)

        # 删除按钮特殊样式（红色调）
        if hasattr(self, 'delete_btn'):
            danger_style = base_style.replace(styles['bg'], '#e74c3c').replace(styles['hover_bg'], '#c0392b')
            self.delete_btn.setStyleSheet(danger_style)

    @staticmethod
    def _get_extra_theme_css(is_dark):
        """生成所有主题通用的补充 CSS（QScrollBar、Slider groove、QStackedWidget 等）"""
        if is_dark:
            return '''
                QScrollBar:vertical {
                    background: #2b2b2b; width: 12px; border: none;
                }
                QScrollBar::handle:vertical {
                    background: #555; border-radius: 6px; min-height: 30px;
                }
                QScrollBar::handle:vertical:hover { background: #666; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
                QScrollBar:horizontal {
                    background: #2b2b2b; height: 12px; border: none;
                }
                QScrollBar::handle:horizontal {
                    background: #555; border-radius: 6px; min-width: 30px;
                }
                QScrollBar::handle:horizontal:hover { background: #666; }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
                QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }
                QSlider::groove:horizontal {
                    background: #555; height: 6px; border-radius: 3px;
                }
                QStackedWidget { background: transparent; border: none; }
                QTextBrowser {
                    background-color: #2b2b2b; color: #e0e0e0; border: 1px solid #555;
                }
                QLabel { background: transparent; }
            '''
        else:
            return '''
                QScrollBar:vertical {
                    background: #f5f5f5; width: 12px; border: none;
                }
                QScrollBar::handle:vertical {
                    background: #ccc; border-radius: 6px; min-height: 30px;
                }
                QScrollBar::handle:vertical:hover { background: #aaa; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
                QScrollBar:horizontal {
                    background: #f5f5f5; height: 12px; border: none;
                }
                QScrollBar::handle:horizontal {
                    background: #ccc; border-radius: 6px; min-width: 30px;
                }
                QScrollBar::handle:horizontal:hover { background: #aaa; }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
                QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }
                QSlider::groove:horizontal {
                    background: #ddd; height: 6px; border-radius: 3px;
                }
                QStackedWidget { background: transparent; border: none; }
                QTextBrowser {
                    background-color: #FFFFFF; color: #333; border: 1px solid #ddd;
                }
                QLabel { background: transparent; }
            '''

    def apply_theme(self):
        """
        加载并应用主题样式
        
        优先从 styles/ 目录加载，失败时回退到硬编码默认样式，
        启动阶段不弹窗阻塞，仅输出日志。
        """
        project_root = get_styles_dir()
        theme_css_file = os.path.join(project_root, self.theme)

        if not os.path.exists(theme_css_file):
            print(f'[StickyNote] 样式文件不存在: {theme_css_file}，使用默认样式')
            self._apply_default_style()
            return

        try:
            with open(theme_css_file, 'r', encoding='utf-8') as f:
                style = f.read()
            if not style.strip():
                print(f'[StickyNote] 样式文件为空: {theme_css_file}，使用默认样式')
                self._apply_default_style()
                return

            is_dark = self.is_dark_theme(style)
            # 追加通用补充 CSS（QScrollBar / QSlider groove / QStackedWidget 等）
            extra_css = self._get_extra_theme_css(is_dark)
            full_style = style + extra_css
            self.setStyleSheet(full_style)
            self.text_edit.setStyleSheet(full_style)
            self.title_edit.setStyleSheet(full_style)
            adaptive_styles = self.get_adaptive_control_styles(is_dark)
            self.apply_adaptive_control_styles(adaptive_styles)
            # md_preview 根据深色/浅色主题设置独立样式
            if hasattr(self, 'md_preview'):
                md_bg = '#2b2b2b' if is_dark else '#FFFFFF'
                md_border = '#555' if is_dark else '#ddd'
                md_text = '#e0e0e0' if is_dark else '#333333'
                self.md_preview.setStyleSheet(f'''
                    QTextBrowser {{
                        background-color: {md_bg};
                        color: {md_text};
                        border: 1px solid {md_border};
                    }}
                ''')
            # 更新边框画笔颜色以匹配主题
            self._border_pen.setColor(QColor(100, 100, 100) if is_dark else QColor(200, 200, 200))
            if hasattr(self, 'font_settings') and self.font_settings:
                self.apply_font()
        except Exception as e:
            print(f'[StickyNote] 加载样式文件失败: {theme_css_file} - {e}')
            self._apply_default_style()

    def _apply_default_style(self):
        """应用硬编码的默认回退样式"""
        default_style = '''
            StickyNote { background-color: #FFF9C4; }
            QLineEdit {
                background-color: #FFFDE7; border: 2px solid #E0D89C;
                border-radius: 5px; padding: 5px; font-family: "Microsoft YaHei";
                font-weight: bold; text-align: center; color: #333333;
            }
            QTextEdit {
                background-color: #FFFDE7; border: 2px solid #E0D89C;
                border-radius: 5px; padding: 5px; font-family: "Microsoft YaHei";
                color: #333333;
            }
        '''
        self.setStyleSheet(default_style)
        self.text_edit.setStyleSheet(default_style)
        self.title_edit.setStyleSheet(default_style)
        is_dark = self.is_dark_theme(default_style)
        adaptive_styles = self.get_adaptive_control_styles(is_dark)
        self.apply_adaptive_control_styles(adaptive_styles)
        # md_preview 根据深色/浅色主题设置独立样式
        if hasattr(self, 'md_preview'):
            md_bg = '#2b2b2b' if is_dark else '#FFFFFF'
            md_border = '#555' if is_dark else '#ddd'
            md_text = '#e0e0e0' if is_dark else '#333333'
            self.md_preview.setStyleSheet(f'''
                QTextBrowser {{
                    background-color: {md_bg};
                    color: {md_text};
                    border: 1px solid {md_border};
                }}
            ''')
        # 更新边框画笔颜色
        self._border_pen.setColor(QColor(100, 100, 100) if is_dark else QColor(200, 200, 200))
        if hasattr(self, 'font_settings') and self.font_settings:
            self.apply_font()

    def set_theme(self, theme_css):
        self.theme = theme_css
        self.apply_theme()
        if not self.is_deleted:
            self.save_note()

    def set_font(self, font_settings):
        self.font_settings = font_settings
        self.apply_font()
        if not self.is_deleted:
            self.save_note()

    def apply_font(self):
        font_settings = getattr(self, 'font_settings', {
            'family': '\u5fae\u8f6f\u96c5\u9ed1', 'size': 12, 'bold': False, 'italic': False
        })
        if not font_settings:
            return
        font_family = font_settings.get('family', '\u5fae\u8f6f\u96c5\u9ed1')
        font_size = font_settings.get('size', 12)
        font_weight = 'bold' if font_settings.get('bold', False) else 'normal'
        font_style = 'italic' if font_settings.get('italic', False) else 'normal'
        font_color = getattr(self, 'font_color', '#000000')
        font_style_sheet = f'''
            font-family: "{font_family}" !important;
            font-size: {font_size}pt !important;
            font-weight: {font_weight} !important;
            font-style: {font_style} !important;
            color: {font_color} !important;
        '''
        self.text_edit.setStyleSheet(self.text_edit.styleSheet() + font_style_sheet)
        self.title_edit.setStyleSheet(self.title_edit.styleSheet() + font_style_sheet)
        base_height = 30
        font_height_factor = 2.5
        calculated_height = max(base_height, int(font_size * font_height_factor))
        self.title_edit.setFixedHeight(calculated_height)
        self.apply_rich_text_format()

    def apply_rich_text_format(self):
        font_settings = getattr(self, 'font_settings', {})
        font_color = getattr(self, 'font_color', '#000000')
        text_char_format = QTextCharFormat()
        if font_settings:
            font = QFont()
            font.setFamily(font_settings.get('family', '\u5fae\u8f6f\u96c5\u9ed1'))
            font.setPointSize(font_settings.get('size', 12))
            font.setBold(font_settings.get('bold', False))
            font.setItalic(font_settings.get('italic', False))
            text_char_format.setFont(font)
        text_char_format.setForeground(QColor(font_color))
        self.text_edit.setCurrentCharFormat(text_char_format)
        title_palette = self.title_edit.palette()
        title_palette.setColor(QPalette.Text, QColor(font_color))
        self.title_edit.setPalette(title_palette)

    # ==================== 数据持久化 ====================

    def load_note(self, preloaded_data=None):
        """
        加载便签数据
        
        Args:
            preloaded_data: 如果提供，直接使用此数据而不读取文件（异步加载优化）
        """
        if preloaded_data is not None:
            return preloaded_data
        if os.path.exists(self.note_file):
            try:
                with open(self.note_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                QMessageBox.warning(self, '\u52a0\u8f7d\u9519\u8bef', f'\u65e0\u6cd5\u52a0\u8f7d\u4fbf\u7b7e\u6587\u4ef6: {e}')
                return self.default_note_data()
        else:
            return self.default_note_data()

    def default_note_data(self):
        return {
            'title': f'\u4fbf\u7b7e {self.note_id}',
            'content': '',
            'plain_content': '',
            'opacity': 0.9,
            'always_on_top': True,
            'locked': False,
            'pinned': False,
            'favorite': False,
            'geometry': None,
            'theme': "soft_yellow.css",
            'title_font_size': 12,
            'content_font_size': 12,
            'auto_format_enabled': True,
            'font_color': '#000000',
            'advanced_toolbar_visible': False,
            'edit_mode': 'richtext',
            'markdown_content': ''
        }

    def save_note(self):
        """
        准备便签数据并触发防抖异步保存。

        数据准备在主线程同步完成（确保 UI 状态准确），
        实际磁盘写入通过 NoteSaveWorker 在后台线程执行。
        """
        # 同步收集 UI 状态
        # 如果处于贴边自动隐藏状态，使用隐藏前的真实位置
        if self.auto_hidden and self._pre_hide_geometry:
            geo = self._pre_hide_geometry
            self.note_data['geometry'] = {
                'x': geo.x(), 'y': geo.y(),
                'width': geo.width(), 'height': geo.height()
            }
        else:
            geometry = self.geometry()
            self.note_data['geometry'] = {
                'x': geometry.x(), 'y': geometry.y(),
                'width': geometry.width(), 'height': geometry.height()
            }
        self.note_data['title'] = self.title_edit.text().strip() or f'\u4fbf\u7b7e {self.note_id}'
        self.note_data['content'] = self.text_edit.toHtml()
        self.note_data['plain_content'] = self.text_edit.toPlainText()
        self.note_data['opacity'] = self.windowOpacity()
        self.note_data['always_on_top'] = self.topmost_checkbox.isChecked()
        self.note_data['theme'] = self.theme
        if hasattr(self, 'title_font_size'):
            self.note_data['title_font_size'] = self.title_font_size
        if hasattr(self, 'content_font_size'):
            self.note_data['content_font_size'] = self.content_font_size
        if hasattr(self, 'font_settings') and self.font_settings:
            self.note_data['font_settings'] = self.font_settings
        self.note_data['auto_format_enabled'] = self.format_checkbox.isChecked()

        # 防抖：重置定时器，500ms 内无新调用才真正写入磁盘
        self._save_timer.start(SAVE_DEBOUNCE_MS)

    def _do_save_to_disk(self):
        """
        真正执行磁盘写入（由防抖定时器触发）。

        将 note_data 深拷贝后交给 NoteSaveWorker 在后台线程写入。
        """
        if self.is_deleted:
            return
        try:
            # 深拷贝数据，避免后台线程访问时数据被修改
            data_copy = copy.deepcopy(self.note_data)
            self._save_worker = NoteSaveWorker(data_copy, self.note_file)
            self._save_worker.start()
        except Exception as e:
            print(f"[StickyNote] 启动保存线程失败: {e}")

    def save_note_sync(self):
        """
        同步保存（用于窗口关闭等关键场景）。

        取消防抖定时器并立即同步写入磁盘。
        """
        self._save_timer.stop()
        # 先收集数据
        self.save_note()
        # 立即停止防抖并同步写入
        self._save_timer.stop()
        try:
            os.makedirs(os.path.dirname(self.note_file), exist_ok=True)
            with open(self.note_file, 'w', encoding='utf-8') as f:
                json.dump(self.note_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[StickyNote] 同步保存失败: {e}")

    # ==================== UI 事件处理 ====================

    def update_title(self):
        self.setWindowTitle(self.title_edit.text().strip() or f'\u4fbf\u7b7e {self.note_id}')
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
        if isinstance(state, bool):
            self.topmost_checkbox.setChecked(state)
        elif state is not None:
            self.topmost_checkbox.setChecked(bool(state))
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.topmost_checkbox.isChecked())
        self.show()
        if not self.is_deleted:
            self.save_note()

    def toggle_auto_format(self, state):
        enabled = self.format_checkbox.isChecked()
        self.text_edit.set_auto_format_enabled(enabled)
        if not self.is_deleted:
            self.save_note()

    def delete_note(self):
        reply = QMessageBox.question(
            self, '\u5220\u9664\u4fbf\u7b7e',
            f"\u786e\u5b9a\u8981\u5220\u9664\u4fbf\u7b7e '{self.note_data.get('title', '')}' \u5417\uff1f",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                # 清理贴边隐藏标签页
                if self.hide_tab is not None:
                    try:
                        self.hide_tab.removeEventFilter(self)
                        self.hide_tab.close()
                    except Exception:
                        logger.debug('关闭隐藏标签页时出错', exc_info=True)
                    self.hide_tab = None
                self.auto_hidden = False
        
                print(f"尝试删除文件: {self.note_file}")
                if os.path.exists(self.note_file):
                    try:
                        with open(self.note_file, 'a'):
                            pass
                    except Exception as e:
                        QMessageBox.warning(self, '\u5220\u9664\u5931\u8d25', f'\u6587\u4ef6\u88ab\u5360\u7528\uff0c\u65e0\u6cd5\u5220\u9664: {e}')
                        return
                    os.remove(self.note_file)
                    QMessageBox.information(self, '\u5220\u9664\u6210\u529f', '\u4fbf\u7b7e\u53ca\u5176\u6587\u4ef6\u5df2\u88ab\u5220\u9664\u3002')
                else:
                    QMessageBox.warning(self, '\u5220\u9664\u5931\u8d25', '\u4fbf\u7b7e\u6587\u4ef6\u4e0d\u5b58\u5728\u3002')
                if self.manager:
                    self.manager.remove_note(self.note_id)
                self.is_deleted = True
                self.close()
            except Exception as e:
                QMessageBox.warning(self, '\u5220\u9664\u9519\u8bef', f'\u65e0\u6cd5\u5220\u9664\u4fbf\u7b7e\u6587\u4ef6: {e}')

    def showEvent(self, event):
        """窗口显示时播放淡入动画，并恢复保存的位置"""
        super().showEvent(event)
        # 在 show() 完成后重新应用保存的位置和大小
        # 部分窗口管理器会在 show 时重置无边框窗口的几何信息
        saved_geometry = self.note_data.get('geometry')
        if saved_geometry and not self.auto_hidden:
            self.setGeometry(QRect(
                saved_geometry.get('x', 100),
                saved_geometry.get('y', 100),
                saved_geometry.get('width', 400),
                saved_geometry.get('height', 300)
            ))
        # 淡入动画
        target_opacity = self.note_data.get('opacity', 0.9)
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b'windowOpacity')
        self._fade_anim.setDuration(200)  # 200ms
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(target_opacity)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.start()

    def _fade_out_and_hide(self):
        """淡出动画后隐藏窗口"""
        self._fade_anim = QPropertyAnimation(self, b'windowOpacity')
        self._fade_anim.setDuration(150)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.InCubic)
        self._fade_anim.finished.connect(self._on_fade_out_finished)
        self._fade_anim.start()

    def _on_fade_out_finished(self):
        """淡出动画完成后真正隐藏窗口"""
        self.hide()
        # 恢复透明度为原始值，以便下次显示
        target_opacity = self.note_data.get('opacity', 0.9)
        self.setWindowOpacity(target_opacity)

    def hide_note(self):
        self._fade_out_and_hide()

    def show_quick_help(self):
        """显示便签快速使用提示"""
        from features.help_content import get_quick_help_text
        QMessageBox.information(self, '使用说明', get_quick_help_text())

    def _update_undo_redo_buttons(self, can_undo, can_redo):
        """根据撤销/重做栈状态更新工具栏按钮"""
        if hasattr(self, 'undo_btn'):
            self.undo_btn.setEnabled(can_undo)
            if can_undo:
                depth = self.undo_redo_manager.get_stack_depth()
                self.undo_btn.setToolTip(f'撤销 (Ctrl+Z) — 可撤销 {depth[0]} 步')
            else:
                self.undo_btn.setToolTip('撤销 (Ctrl+Z)')
        if hasattr(self, 'redo_btn'):
            self.redo_btn.setEnabled(can_redo)
            if can_redo:
                depth = self.undo_redo_manager.get_stack_depth()
                self.redo_btn.setToolTip(f'重做 (Ctrl+Y) — 可重做 {depth[1]} 步')
            else:
                self.redo_btn.setToolTip('重做 (Ctrl+Y)')

    # ==================== 富文本工具栏辅助方法 ====================

    def _toggle_underline(self):
        """切换下划线"""
        self.rich_text.toggle_underline()
        # 同步按钮状态
        fmt = self.text_edit.currentCharFormat()
        self.underline_btn.setChecked(fmt.fontUnderline())
        if not self.is_deleted:
            self.save_note()

    def _toggle_strikethrough(self):
        """切换删除线"""
        self.rich_text.toggle_strikethrough()
        fmt = self.text_edit.currentCharFormat()
        self.strikethrough_btn.setChecked(fmt.fontStrikeOut())
        if not self.is_deleted:
            self.save_note()

    def _choose_highlight_color(self):
        """选择高亮颜色"""
        color = QColorDialog.getColor(QColor('#FFFF00'), self, '选择高亮颜色')
        if color.isValid():
            self.rich_text.set_highlight_color(color)
            if not self.is_deleted:
                self.save_note()

    def _insert_hyperlink_dialog(self):
        """插入超链接对话框"""
        url, ok1 = QInputDialog.getText(self, '插入链接', 'URL:')
        if not ok1 or not url:
            return
        text, ok2 = QInputDialog.getText(self, '插入链接', '显示文本:', text=url)
        if ok2 and text:
            self.rich_text.insert_hyperlink(url, text)
            if not self.is_deleted:
                self.save_note()

    def _insert_image_dialog(self):
        """插入图片对话框"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, '选择图片', '',
            '图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp)'
        )
        if file_path:
            self.rich_text.insert_image_from_file(
                file_path, strategy='base64',
                notes_dir=self.notes_dir, note_id=self.note_id
            )
            if not self.is_deleted:
                self.save_note()

    def _toggle_markdown_mode(self):
        """切换 Markdown 预览模式"""
        self.is_markdown_mode = not self.is_markdown_mode
        if self.is_markdown_mode:
            # 切换到 Markdown 预览
            if self.md_renderer is None:
                try:
                    from features.markdown_renderer import MarkdownRenderer
                    self.md_renderer = MarkdownRenderer()
                except ImportError:
                    self.md_renderer = None
            md_text = self.text_edit.toPlainText()
            if self.md_renderer:
                body_html, css = self.md_renderer.render_for_qt(md_text)
                # 使用 setDefaultStyleSheet + body-only HTML 确保 QTextBrowser 正确渲染样式
                self.md_preview.document().setDefaultStyleSheet(css)
                self.md_preview.setHtml(body_html)
            else:
                self.md_preview.setHtml(f'<pre>{md_text}</pre>')
            self.editor_stack.setCurrentIndex(1)
            self.md_toggle_btn.setChecked(True)
            self.md_toggle_btn.setToolTip('切换回富文本编辑')
        else:
            # 切换回富文本编辑
            self.editor_stack.setCurrentIndex(0)
            self.md_toggle_btn.setChecked(False)
            self.md_toggle_btn.setToolTip('切换 Markdown 预览')

    def _show_backlinks(self):
        """显示便签反向链接"""
        if not self.manager or not hasattr(self.manager, 'link_manager'):
            QMessageBox.information(self, '反向链接', '链接功能未启用')
            return
        try:
            title = self.title_edit.text().strip()
            backlinks = self.manager.link_manager.get_backlinks(self.note_id, title)
            if backlinks:
                lines = [f'• {link_title} (ID: {link_id})' for link_id, link_title in backlinks]
                QMessageBox.information(self, f'“{title}” 的反向链接',
                                       '\n'.join(lines))
            else:
                QMessageBox.information(self, f'“{title}” 的反向链接',
                                       '暂无其他便签链接到此便签')
        except Exception as e:
            logger.debug(f'获取反向链接失败: {e}')
            QMessageBox.information(self, '反向链接', f'无法获取反向链接: {e}')

    def _toggle_lock(self):
        """切换便签锁定状态"""
        self.is_locked = not self.is_locked
        self.note_data['locked'] = self.is_locked
        self.lock_btn.setText('🔒' if self.is_locked else '🔓')
        self.lock_btn.setToolTip('解锁便签' if self.is_locked else '锁定便签')
        self.title_edit.setReadOnly(self.is_locked)
        self.text_edit.setReadOnly(self.is_locked)
        if not self.is_deleted:
            self.save_note()

    def toggle_pin(self):
        """切换便签置顶状态"""
        self.is_pinned = not self.is_pinned
        self.note_data['pinned'] = self.is_pinned
        if not self.is_deleted:
            self.save_note()
        if self.manager:
            self.manager.update_tray_menu()

    def toggle_favorite(self):
        """切换便签收藏状态"""
        self.is_favorite = not self.is_favorite
        self.note_data['favorite'] = self.is_favorite
        if not self.is_deleted:
            self.save_note()
        if self.manager:
            self.manager.update_tray_menu()

    def open_reminder_dialog(self):
        """打开提醒设置对话框"""
        from features.reminder import ReminderDialog
        dialog = ReminderDialog(self, parent=self)
        if dialog.exec_() == ReminderDialog.Accepted:
            self.update_reminder_display()

    def open_tag_selector(self):
        """打开标签选择器"""
        from features.tag import NoteTagSelector
        dialog = NoteTagSelector(self, self.manager, parent=self)
        if dialog.exec_() == NoteTagSelector.Accepted:
            self.refresh_tag_chips()
            if self.manager:
                self.manager.update_tray_menu()

    def refresh_tag_chips(self):
        """刷新标签芯片显示（版本号固定左侧，标签在右侧排列）"""
        # 清除现有标签芯片（保留 index 0 的 version_label 和最后的 stretch）
        while self.tags_layout.count() > 2:
            item = self.tags_layout.takeAt(1)  # 从 index 1 开始删除
            if item and item.widget():
                item.widget().deleteLater()

        tags = self.note_data.get('tags', [])
        if not self.manager or not self.manager.tag_manager:
            return
        for tag_name in tags:
            color = self.manager.tag_manager.get_tag_color(tag_name)
            chip = TagChipWidget(tag_name, color, self)
            chip.removed.connect(self._on_tag_removed)
            # 插入在 stretch 之前（即 count()-1 的位置）
            self.tags_layout.insertWidget(self.tags_layout.count() - 1, chip)

    def _on_tag_removed(self, tag_name):
        """标签芯片被点击移除"""
        tags = self.note_data.get('tags', [])
        if tag_name in tags:
            tags.remove(tag_name)
            self.note_data['tags'] = tags
            if not self.is_deleted:
                self.save_note()
            self.refresh_tag_chips()
            if self.manager:
                self.manager.update_tray_menu()

    def update_reminder_display(self):
        """更新提醒按钮状态显示"""
        if not self.manager or not self.manager.reminder_manager:
            return
        info = self.manager.reminder_manager.get_reminder_info(self)
        if info['enabled']:
            self.reminder_btn.setToolTip(info['text'])
            self.reminder_btn.setStyleSheet(
                'QPushButton { background-color: #007acc; color: white; border-radius: 3px; font-size: 14pt; }'
            )
        else:
            self.reminder_btn.setToolTip('设置提醒')
            self.reminder_btn.setStyleSheet('')

    # ==================== 窗口拖拽和调整大小 ====================

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 用户点击便签内容，取消悬停恢复的自动缩回状态
            self._hover_restored = False
            self._cancel_rehide_timer()

            widget = self.childAt(event.pos())
            if widget in [self.title_edit, self.text_edit]:
                super().mousePressEvent(event)
                return
            self.drag_pos = event.globalPos()
            self.initial_geometry = self.geometry()
            rect = self.rect()
            x, y = event.x(), event.y()
            margin = RESIZE_MARGIN
            self.resize_dir = None
            if x < margin and y < margin:
                self.resizing, self.resize_dir = True, 'top_left'
            elif x > rect.width() - margin and y < margin:
                self.resizing, self.resize_dir = True, 'top_right'
            elif x < margin and y > rect.height() - margin:
                self.resizing, self.resize_dir = True, 'bottom_left'
            elif x > rect.width() - margin and y > rect.height() - margin:
                self.resizing, self.resize_dir = True, 'bottom_right'
            elif x < margin:
                self.resizing, self.resize_dir = True, 'left'
            elif x > rect.width() - margin:
                self.resizing, self.resize_dir = True, 'right'
            elif y < margin:
                self.resizing, self.resize_dir = True, 'top'
            elif y > rect.height() - margin:
                self.resizing, self.resize_dir = True, 'bottom'
            else:
                self.dragging = True
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        widget = self.childAt(event.pos())
        if widget in [self.title_edit, self.text_edit]:
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
            super().mouseReleaseEvent(event)
            return
        was_dragging = self.dragging
        self.dragging = False
        self.resizing = False
        self.resize_dir = None
        self.setCursor(QCursor(Qt.ArrowCursor))
        # 拖拽结束时执行窗口吸附和贴边检测
        if was_dragging:
            self._apply_snapping()
            self._check_auto_hide()
        if not self.is_deleted:
            self.save_note()
        event.accept()

    def _apply_snapping(self):
        """执行窗口吸附：屏幕边缘 + 其他便签"""
        current_geo = self.geometry()
        new_geo = QRect(current_geo)

        # 1. 吸附屏幕边缘
        desktop = QApplication.desktop()
        if desktop:
            screen_geo = self._get_screen_geometry()
            # 左边缘
            if abs(new_geo.left() - screen_geo.left()) <= SNAP_THRESHOLD:
                new_geo.moveLeft(screen_geo.left())
            # 右边缘
            if abs(new_geo.right() - screen_geo.right()) <= SNAP_THRESHOLD:
                new_geo.moveRight(screen_geo.right())
            # 上边缘
            if abs(new_geo.top() - screen_geo.top()) <= SNAP_THRESHOLD:
                new_geo.moveTop(screen_geo.top())
            # 下边缘
            if abs(new_geo.bottom() - screen_geo.bottom()) <= SNAP_THRESHOLD:
                new_geo.moveBottom(screen_geo.bottom())

        # 2. 吸附其他便签窗口
        if self.manager:
            for other_id, other_note in self.manager.notes.items():
                if other_id == self.note_id or other_note.is_deleted:
                    continue
                if not other_note.isVisible():
                    continue
                other_geo = other_note.geometry()
                new_geo = self._snap_to_window(new_geo, other_geo)

        # 只在位置发生变化时移动
        if new_geo != current_geo:
            self.setGeometry(new_geo)

    def _snap_to_window(self, my_geo: QRect, other_geo: QRect) -> QRect:
        """
        吸附到另一个窗口的边缘
        
        检测：左边对齐、右边对齐、上边对齐、下边对齐、
              左贴右、右贴左、上贴下、下贴上
        """
        result = QRect(my_geo)

        # 水平方向：我的左边吸附到对方的右边
        if abs(result.left() - other_geo.right()) <= SNAP_THRESHOLD:
            result.moveLeft(other_geo.right())
        # 我的右边吸附到对方的左边
        elif abs(result.right() - other_geo.left()) <= SNAP_THRESHOLD:
            result.moveRight(other_geo.left())

        # 垂直方向：我的上边吸附到对方的下边
        if abs(result.top() - other_geo.bottom()) <= SNAP_THRESHOLD:
            result.moveTop(other_geo.bottom())
        # 我的下边吸附到对方的上边
        elif abs(result.bottom() - other_geo.top()) <= SNAP_THRESHOLD:
            result.moveBottom(other_geo.top())

        # 边缘对齐（同列/同行）
        if abs(result.left() - other_geo.left()) <= SNAP_THRESHOLD:
            result.moveLeft(other_geo.left())
        elif abs(result.right() - other_geo.right()) <= SNAP_THRESHOLD:
            result.moveRight(other_geo.right())
        if abs(result.top() - other_geo.top()) <= SNAP_THRESHOLD:
            result.moveTop(other_geo.top())
        elif abs(result.bottom() - other_geo.bottom()) <= SNAP_THRESHOLD:
            result.moveBottom(other_geo.bottom())

        return result

    # ==================== 贴边自动隐藏 ====================

    # 触发自动隐藏的屏幕边缘距离阈值（像素）
    AUTO_HIDE_THRESHOLD = 3

    def _get_screen_geometry(self):
        """获取当前屏幕可用几何区域（1秒缓存）"""
        now = time.time()
        if self._screen_geo_cache is not None and (now - self._screen_geo_cache_time) < 1.0:
            return self._screen_geo_cache
        desktop = QApplication.desktop()
        if desktop:
            self._screen_geo_cache = desktop.availableGeometry(self)
            self._screen_geo_cache_time = now
            return self._screen_geo_cache
        return None

    def _check_auto_hide(self):
        """
        拖拽结束后检测是否贴到屏幕边缘，触发自动隐藏。
        
        当便签边缘距离屏幕边缘 ≤ AUTO_HIDE_THRESHOLD 时触发。
        优先级：左 > 右 > 上 > 下
        """
        if self.auto_hidden:
            return

        geo = self.geometry()
        desktop = QApplication.desktop()
        if not desktop:
            return
        screen = self._get_screen_geometry()

        threshold = self.AUTO_HIDE_THRESHOLD

        # 左右边缘优先
        if geo.left() <= screen.left() + threshold:
            self._auto_hide_to_edge('left')
        elif geo.right() >= screen.right() - threshold:
            self._auto_hide_to_edge('right')
        elif geo.top() <= screen.top() + threshold:
            self._auto_hide_to_edge('top')
        elif geo.bottom() >= screen.bottom() - threshold:
            self._auto_hide_to_edge('bottom')

    def _auto_hide_to_edge(self, edge):
        """
        执行贴边自动隐藏。
        
        流程：保存当前位置 → 创建标签页 → 动画滑出主窗口 → 显示标签页
        """
        if self.auto_hidden:
            return

        self.auto_hidden = True
        self.hidden_edge = edge
        self._pre_hide_geometry = self.geometry()

        # 创建并显示标签页
        self._create_hide_tab()
        self._position_hide_tab()
        self.hide_tab.show()

        # 动画滑出主窗口
        self._slide_out_animation(edge)

    def _create_hide_tab(self):
        """
        创建隐藏状态下的标签页小窗口。
        
        标签页是一个独立的小窗口，显示便签标题缩写和方向箭头，
        始终置顶，方便用户找到隐藏的便签。
        """
        if self.hide_tab is not None:
            return

        title = self.note_data.get('title', f'便签 {self.note_id}')
        short_title = title[:8] + ('…' if len(title) > 8 else '')

        self.hide_tab = QWidget(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.hide_tab.setFixedSize(130, 28)
        self.hide_tab.setMouseTracking(True)

        # 根据主题设置颜色
        is_dark = getattr(self, '_is_dark_theme', False)
        bg = '#3a3a3a' if is_dark else '#FFFDE7'
        fg = '#FFFFFF' if is_dark else '#333333'
        border = '#555555' if is_dark else '#B0B0B0'

        self.hide_tab.setStyleSheet(f'''
            QWidget {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 4px;
            }}
        ''')

        layout = QHBoxLayout()
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        # 方向箭头
        arrow_map = {'left': '▶', 'right': '◀', 'top': '▼', 'bottom': '▲'}
        arrow = arrow_map.get(self.hidden_edge, '▶')

        arrow_label = QLabel(arrow)
        arrow_label.setFixedWidth(16)
        arrow_label.setStyleSheet(f'color: {fg}; font-size: 10pt; border: none;')
        layout.addWidget(arrow_label)

        title_label = QLabel(short_title)
        title_label.setStyleSheet(f'color: {fg}; font-size: 9pt; border: none;')
        layout.addWidget(title_label)
        layout.addStretch()

        self.hide_tab.setLayout(layout)

        # 安装事件过滤器以检测悬停和点击
        self.hide_tab.installEventFilter(self)

    def _position_hide_tab(self):
        """根据隐藏边缘计算标签页的屏幕位置"""
        if self.hide_tab is None:
            return

        desktop = QApplication.desktop()
        if not desktop:
            return
        screen = self._get_screen_geometry()
        pre_geo = self._pre_hide_geometry
        tab_w, tab_h = 130, 28

        if self.hidden_edge == 'left':
            x = screen.left()
            y = pre_geo.top() + (pre_geo.height() - tab_h) // 2
        elif self.hidden_edge == 'right':
            x = screen.right() - tab_w
            y = pre_geo.top() + (pre_geo.height() - tab_h) // 2
        elif self.hidden_edge == 'top':
            x = pre_geo.left() + (pre_geo.width() - tab_w) // 2
            y = screen.top()
        else:  # bottom
            x = pre_geo.left() + (pre_geo.width() - tab_w) // 2
            y = screen.bottom() - tab_h

        # 确保标签页在屏幕可视范围内
        x = max(screen.left(), min(x, screen.right() - tab_w))
        y = max(screen.top(), min(y, screen.bottom() - tab_h))

        self.hide_tab.move(x, y)

    def _slide_out_animation(self, edge):
        """便签主窗口滑出屏幕的动画"""
        desktop = QApplication.desktop()
        if not desktop:
            return
        screen = self._get_screen_geometry()
        current_pos = self.pos()
        w, h = self.width(), self.height()

        if edge == 'left':
            target = QPoint(screen.left() - w + 1, current_pos.y())
        elif edge == 'right':
            target = QPoint(screen.right() - 1, current_pos.y())
        elif edge == 'top':
            target = QPoint(current_pos.x(), screen.top() - h + 1)
        else:  # bottom
            target = QPoint(current_pos.x(), screen.bottom() - 1)

        self._slide_anim = QPropertyAnimation(self, b'pos')
        self._slide_anim.setDuration(250)
        self._slide_anim.setStartValue(current_pos)
        self._slide_anim.setEndValue(target)
        self._slide_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._slide_anim.start()

    def _restore_from_auto_hide(self, hover_triggered=False):
        """
        从自动隐藏状态恢复便签。
        
        Args:
            hover_triggered: True=悬停触发（离开便签区域会自动缩回），
                            False=点击触发（保持展开）
        """
        if not self.auto_hidden:
            return

        self.auto_hidden = False
        self.hidden_edge = None
        self._hover_restored = hover_triggered

        # 取消之前的缩回定时器
        self._cancel_rehide_timer()

        # 隐藏并清理标签页
        if self.hide_tab is not None:
            self.hide_tab.hide()
            self.hide_tab.removeEventFilter(self)
            self.hide_tab.deleteLater()
            self.hide_tab = None

        # 动画滑回原位
        if self._pre_hide_geometry:
            target_pos = self._pre_hide_geometry.topLeft()
            # 确保目标位置在屏幕范围内
            desktop = QApplication.desktop()
            if desktop:
                screen = self._get_screen_geometry()
                w, h = self._pre_hide_geometry.width(), self._pre_hide_geometry.height()
                target_x = max(screen.left(), min(target_pos.x(), screen.right() - w))
                target_y = max(screen.top(), min(target_pos.y(), screen.bottom() - h))
                target_pos = QPoint(target_x, target_y)
        else:
            # 无历史位置，恢复到屏幕中央
            desktop = QApplication.desktop()
            if desktop:
                screen = self._get_screen_geometry()
                target_pos = QPoint(
                    screen.left() + (screen.width() - self.width()) // 2,
                    screen.top() + (screen.height() - self.height()) // 2
                )
            else:
                target_pos = QPoint(200, 200)

        self._slide_anim = QPropertyAnimation(self, b'pos')
        self._slide_anim.setDuration(250)
        self._slide_anim.setStartValue(self.pos())
        self._slide_anim.setEndValue(target_pos)
        self._slide_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._slide_anim.finished.connect(self._on_restore_finished)
        self._slide_anim.start()

    def _on_restore_finished(self):
        """恢复动画完成后的清理"""
        self._pre_hide_geometry = None
        self.setWindowOpacity(self.note_data.get('opacity', 0.9))
        self.raise_()
        self.activateWindow()

        # 如果是悬停触发的恢复，启动缩回检测
        if self._hover_restored:
            self._schedule_rehide_check()

    def eventFilter(self, obj, event):
        """
        事件过滤器：处理隐藏标签页的鼠标悬停和点击。
        
        悬停 300ms 后自动展开便签（离开便签区域会自动缩回），
        单击立即展开且保持展开（不会自动缩回）。
        """
        if obj == self.hide_tab and self.auto_hidden:
            if event.type() == QEvent.Enter:
                # 悬停延迟展开
                self._hover_restore_timer = QTimer(self)
                self._hover_restore_timer.setSingleShot(True)
                self._hover_restore_timer.timeout.connect(
                    lambda: self._restore_from_auto_hide(hover_triggered=True)
                )
                self._hover_restore_timer.start(300)
            elif event.type() == QEvent.Leave:
                # 鼠标离开，取消悬停展开
                if hasattr(self, '_hover_restore_timer') and self._hover_restore_timer is not None:
                    self._hover_restore_timer.stop()
            elif event.type() == QEvent.MouseButtonPress:
                # 点击立即展开，且保持展开（不自动缩回）
                if hasattr(self, '_hover_restore_timer') and self._hover_restore_timer is not None:
                    self._hover_restore_timer.stop()
                self._restore_from_auto_hide(hover_triggered=False)
                return True
        return super().eventFilter(obj, event)

    def perform_resize(self, global_pos):
        delta = global_pos - self.drag_pos
        geometry = QRect(self.initial_geometry)
        min_width, min_height = 100, 120
        new_x = geometry.x() + delta.x()
        new_y = geometry.y() + delta.y()
        new_width = geometry.width() + delta.x()
        new_height = geometry.height() + delta.y()
        if self.resize_dir == 'top_left':
            new_width = geometry.width() - delta.x()
            new_height = geometry.height() - delta.y()
            if new_width >= min_width and new_height >= min_height:
                geometry.setRect(new_x, new_y, new_width, new_height)
        elif self.resize_dir == 'top_right':
            new_height = geometry.height() - delta.y()
            if new_width >= min_width and new_height >= min_height:
                geometry.setRect(geometry.x(), new_y, new_width, new_height)
        elif self.resize_dir == 'bottom_left':
            new_width = geometry.width() - delta.x()
            if new_width >= min_width and new_height >= min_height:
                geometry.setRect(new_x, geometry.y(), new_width, new_height)
        elif self.resize_dir == 'bottom_right':
            if new_width >= min_width and new_height >= min_height:
                geometry.setRect(geometry.x(), geometry.y(), new_width, new_height)
        elif self.resize_dir == 'left':
            new_width = geometry.width() - delta.x()
            if new_width >= min_width:
                geometry.setRect(new_x, geometry.y(), new_width, geometry.height())
        elif self.resize_dir == 'right':
            if new_width >= min_width:
                geometry.setWidth(new_width)
        elif self.resize_dir == 'top':
            new_height = geometry.height() - delta.y()
            if new_height >= min_height:
                geometry.setRect(geometry.x(), new_y, geometry.width(), new_height)
        elif self.resize_dir == 'bottom':
            if new_height >= min_height:
                geometry.setHeight(new_height)
        self.setGeometry(geometry)
        if not self.is_deleted:
            self.save_note()

    def update_cursor(self, event):
        rect = self.rect()
        margin = RESIZE_MARGIN
        x, y = event.x(), event.y()
        top = y < margin
        bottom = y > rect.height() - margin
        left = x < margin
        right = x > rect.width() - margin
        if top and left:
            self.setCursor(QCursor(Qt.SizeFDiagCursor))
        elif top and right:
            self.setCursor(QCursor(Qt.SizeBDiagCursor))
        elif bottom and left:
            self.setCursor(QCursor(Qt.SizeBDiagCursor))
        elif bottom and right:
            self.setCursor(QCursor(Qt.SizeFDiagCursor))
        elif left:
            self.setCursor(QCursor(Qt.SizeHorCursor))
        elif right:
            self.setCursor(QCursor(Qt.SizeHorCursor))
        elif top:
            self.setCursor(QCursor(Qt.SizeVerCursor))
        elif bottom:
            self.setCursor(QCursor(Qt.SizeVerCursor))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))

    # ==================== 悬停展开自动缩回 ====================

    def _schedule_rehide_check(self):
        """
        悬停恢复后等待 500ms，检查鼠标是否在便签区域内。
        若不在则触发自动缩回。
        """
        self._cancel_rehide_timer()
        self._auto_rehide_timer = QTimer(self)
        self._auto_rehide_timer.setSingleShot(True)
        self._auto_rehide_timer.timeout.connect(self._check_and_rehide)
        self._auto_rehide_timer.start(500)

    def _check_and_rehide(self):
        """检查鼠标位置，若不在便签区域内则自动缩回隐藏"""
        if not self._hover_restored:
            return
        # 检查鼠标是否在便签区域内
        cursor_pos = QCursor.pos()
        note_geo = self.geometry()
        if not note_geo.contains(cursor_pos):
            self._auto_rehide()

    def _auto_rehide(self):
        """自动将便签缩回之前隐藏的边缘"""
        if self.auto_hidden or self._pre_hide_geometry is None:
            return

        self._hover_restored = False
        self._cancel_rehide_timer()

        # 确定隐藏边缘
        desktop = QApplication.desktop()
        if not desktop:
            return
        screen = self._get_screen_geometry()
        geo = self.geometry()

        # 根据当前位置判断最近边缘
        dist_left = abs(geo.left() - screen.left())
        dist_right = abs(geo.right() - screen.right())
        dist_top = abs(geo.top() - screen.top())
        dist_bottom = abs(geo.bottom() - screen.bottom())
        edges = [
            (dist_left, 'left'), (dist_right, 'right'),
            (dist_top, 'top'), (dist_bottom, 'bottom')
        ]
        edge = min(edges, key=lambda x: x[0])[1]

        self._pre_hide_geometry = geo
        self.auto_hidden = True
        self.hidden_edge = edge

        # 创建并显示标签页
        self._create_hide_tab()
        self._position_hide_tab()
        self.hide_tab.show()

        # 动画滑出
        self._slide_out_animation(edge)

    def _cancel_rehide_timer(self):
        """取消自动缩回定时器"""
        if self._auto_rehide_timer is not None:
            self._auto_rehide_timer.stop()
            self._auto_rehide_timer = None

    # ==================== 鼠标事件 ====================

    def enterEvent(self, event):
        # 悬停展开后鼠标进入便签区域，取消自动缩回
        if self._hover_restored:
            self._cancel_rehide_timer()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.resizing and not self.dragging:
            self.setCursor(QCursor(Qt.ArrowCursor))
        # 悬停展开后鼠标离开便签区域，启动缩回定时器
        if self._hover_restored and not self.auto_hidden:
            self._schedule_rehide_check()
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(self._border_pen)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

    # ==================== 右键上下文菜单 ====================

    def contextMenuEvent(self, event):
        """右键上下文菜单"""
        menu = QMenu(self)

        # 复制/粘贴
        copy_action = QAction('复制全部内容', self)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(
            self.text_edit.toPlainText()
        ))
        menu.addAction(copy_action)

        paste_action = QAction('粘贴', self)
        paste_action.triggered.connect(lambda: self.text_edit.paste())
        menu.addAction(paste_action)

        menu.addSeparator()

        # 置顶
        pin_action = QAction('📌 置顶' if not self.is_pinned else '📌 取消置顶', self)
        pin_action.triggered.connect(self.toggle_pin)
        menu.addAction(pin_action)

        # 收藏
        fav_action = QAction('⭐ 收藏' if not self.is_favorite else '⭐ 取消收藏', self)
        fav_action.triggered.connect(self.toggle_favorite)
        menu.addAction(fav_action)

        # 锁定
        lock_action = QAction('🔒 锁定' if not self.is_locked else '🔓 解锁', self)
        lock_action.triggered.connect(self._toggle_lock)
        menu.addAction(lock_action)

        menu.addSeparator()

        # 主题子菜单
        theme_menu = QMenu('切换主题', menu)
        if self.manager:
            try:
                themes = self.manager.get_available_themes()
                for theme_name, css_file in themes.items():
                    theme_action = QAction(theme_name, theme_menu)
                    theme_action.setCheckable(True)
                    theme_action.setChecked(css_file == self.theme)
                    theme_action.triggered.connect(
                        lambda checked, f=css_file: self.set_theme(f)
                    )
                    theme_menu.addAction(theme_action)
            except Exception:
                logger.debug('加载主题列表时出错', exc_info=True)
        menu.addMenu(theme_menu)

        # 字体大小快速调整
        font_menu = QMenu('字体设置', menu)
        inc_font = QAction('增大字体 A+', font_menu)
        inc_font.triggered.connect(self.increase_font_size)
        font_menu.addAction(inc_font)
        dec_font = QAction('减小字体 A-', font_menu)
        dec_font.triggered.connect(self.decrease_font_size)
        font_menu.addAction(dec_font)
        menu.addMenu(font_menu)

        menu.addSeparator()

        # 置顶开关
        topmost_action = QAction('总在最前', self)
        topmost_action.setCheckable(True)
        topmost_action.setChecked(self.note_data.get('always_on_top', True))
        topmost_action.triggered.connect(
            lambda checked: self.toggle_always_on_top(checked)
        )
        menu.addAction(topmost_action)

        # 透明度（互斥组：同一时间只有一个选中）
        opacity_menu = QMenu('透明度', menu)
        opacity_group = None
        try:
            from PyQt5.QtWidgets import QActionGroup
            opacity_group = QActionGroup(opacity_menu)
            opacity_group.setExclusive(True)
        except Exception:
            logger.debug('创建透明度菜单组时出错', exc_info=True)
        for pct in [100, 90, 80, 70, 60, 50, 40, 30]:
            op_action = QAction(f'{pct}%', opacity_menu)
            op_action.setCheckable(True)
            op_action.setChecked(int(self.windowOpacity() * 100) == pct)
            if opacity_group:
                opacity_group.addAction(op_action)
            op_action.triggered.connect(
                lambda checked, v=pct: self.set_opacity(v / 100.0)
            )
            opacity_menu.addAction(op_action)
        menu.addMenu(opacity_menu)

        menu.addSeparator()

        # 标签和提醒
        tag_action = QAction('🏷 设置标签', self)
        tag_action.triggered.connect(self.open_tag_selector)
        menu.addAction(tag_action)

        reminder_action = QAction('⏰ 设置提醒', self)
        reminder_action.triggered.connect(self.open_reminder_dialog)
        menu.addAction(reminder_action)

        menu.addSeparator()

        # 删除和隐藏
        hide_action = QAction('隐藏便签', self)
        hide_action.triggered.connect(self.hide_note)
        menu.addAction(hide_action)

        delete_action = QAction('删除便签', self)
        delete_action.triggered.connect(self.delete_note)
        menu.addAction(delete_action)

        menu.exec_(event.globalPos())

    def set_opacity(self, opacity: float):
        """设置窗口透明度"""
        self.setWindowOpacity(opacity)
        self.transparency_slider.setValue(int(opacity * 100))
        if not self.is_deleted:
            self.save_note()

    def closeEvent(self, event):
        if self.is_deleted:
            # 清理贴边隐藏标签页
            if self.hide_tab is not None:
                try:
                    self.hide_tab.removeEventFilter(self)
                    self.hide_tab.close()
                except Exception:
                    logger.debug('关闭隐藏标签页时出错', exc_info=True)
                self.hide_tab = None

            position_manager = get_position_manager()
            position_manager.unregister_window_position(
                self.note_id,
                QPoint(self.x(), self.y()),
                QSize(self.width(), self.height())
            )
            # 停止防抖和后台保存线程，执行同步保存
            self._save_timer.stop()
            super().closeEvent(event)
        else:
            event.ignore()
            self._fade_out_and_hide()
            if self.manager:
                self.manager.tray_icon.showMessage(
                    "\u4fbf\u7b7e\u5df2\u9690\u85cf",
                    f"\u4fbf\u7b7e '{self.note_data.get('title', '')}' \u5df2\u88ab\u9690\u85cf\u3002",
                    QSystemTrayIcon.Information, 2000
                )

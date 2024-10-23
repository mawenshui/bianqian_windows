import sys
import os
import json
import winreg
from functools import partial
from PyQt5.QtWidgets import (
    QApplication, QWidget, QTextEdit, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QMessageBox, QMenu, QAction,
    QCheckBox, QSystemTrayIcon, QDialog, QFormLayout,
    QLineEdit, QStyle, QColorDialog, QComboBox
)
from PyQt5.QtCore import Qt, QCoreApplication, QPoint, QRect, QMimeData  
from PyQt5.QtGui import QFont, QColor, QPalette, QIcon, QPainter, QPen, QCursor, QGuiApplication

# 定义常量用于窗口调整大小
RESIZE_MARGIN = 10  # 调整大小检测边界宽度

class PlainLineEdit(QLineEdit):
    def paste(self):
        clipboard = QApplication.clipboard()
        plain_text = clipboard.text()
        self.insert(plain_text)

class PlainTextEdit(QTextEdit):
    def paste(self):
        clipboard = QApplication.clipboard()
        plain_text = clipboard.text()
        self.insertPlainText(plain_text)

    def insertFromMimeData(self, source: QMimeData):
        if source.hasText():
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
        self.title_edit.setFixedHeight(40)  # 增加高度以适应字体
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

        # 设置字体大小
        self.title_font_size = self.note_data.get('title_font_size', 12)  # 新增：标题字体大小
        self.content_font_size = self.note_data.get('content_font_size', 12)  # 新增：内容字体大小
        self.set_font_size(self.title_font_size, self.content_font_size)

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
        else:
            self.resize(400, 300)  # 默认大小宽度调整为400

            # **修改部分开始：将新便签置于屏幕中心**
            screen = QGuiApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                x = (screen_geometry.width() - self.width()) // 2
                y = (screen_geometry.height() - self.height()) // 2
                self.move(screen_geometry.x() + x, screen_geometry.y() + y)
            else:
                # 如果无法获取屏幕几何信息，则默认放置
                self.move(100, 100)
            # **修改部分结束**

    def set_font_size(self, title_size, content_size):
        title_font = QFont()
        title_font.setPointSize(title_size)
        title_font.setBold(True)  # 保持标题加粗
        self.title_edit.setFont(title_font)

        content_font = QFont()
        content_font.setPointSize(content_size)
        self.text_edit.setFont(content_font)

    def increase_font_size(self):
        # 分别增加标题和内容的字体大小
        self.title_font_size += 1
        self.content_font_size += 1
        self.set_font_size(self.title_font_size, self.content_font_size)
        self.note_data['title_font_size'] = self.title_font_size
        self.note_data['content_font_size'] = self.content_font_size
        if not self.is_deleted:
            self.save_note()

    def decrease_font_size(self):
        # 分别减小标题和内容的字体大小，最小不能小于6
        if self.title_font_size > 6:
            self.title_font_size -= 1
        if self.content_font_size > 6:
            self.content_font_size -= 1
        self.set_font_size(self.title_font_size, self.content_font_size)
        self.note_data['title_font_size'] = self.title_font_size
        self.note_data['content_font_size'] = self.content_font_size
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
            'content_font_size': 12  # 新增：内容字体大小
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
        self.note_data['title_font_size'] = self.title_font_size  # 保存标题字体大小
        self.note_data['content_font_size'] = self.content_font_size  # 保存内容字体大小
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
    # **新增方法结束**

class SettingsDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowModality(Qt.NonModal)  # 设置为非模态对话框
        self.initUI()

    def initUI(self):
        self.setWindowTitle('设置')
        self.setFixedSize(400, 200)  # 调整高度
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)  # 始终置顶
        layout = QVBoxLayout()

        form_layout = QFormLayout()

        # 主题选择
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
        self.theme_combo.currentIndexChanged.connect(self.change_theme)

        form_layout.addRow(self.theme_label, self.theme_combo)

        layout.addLayout(form_layout)

        # 添加伸缩项以便作者标签位于最底端
        layout.addStretch()

        # 作者标签
        author_label = QLabel("By：MaWenshui")
        author_label.setAlignment(Qt.AlignCenter)
        author_label.setStyleSheet("color: gray; font-size: 10pt;")
        layout.addWidget(author_label)

        self.setLayout(layout)

    def load_themes(self):
        self.themes = self.manager.get_available_themes()
        self.theme_combo.clear()
        for theme_name in self.themes.keys():
            self.theme_combo.addItem(theme_name)

    def change_theme(self):
        selected_theme_name = self.theme_combo.currentText()
        selected_theme_css = self.themes.get(selected_theme_name, "soft_yellow.css")
        self.manager.set_default_theme(selected_theme_css)
        self.manager.apply_theme_to_all_notes()

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

        # 设置托盘图标和菜单
        self.setup_tray_icon()

        # 加载已有便签
        self.load_notes()

        # 启动时默认创建一个便签（如果没有）
        if not self.notes:
            self.add_note()

        # 初始化设置对话框实例为空
        self.settings_dialog = None

    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self.icon, parent=self.app)
        self.tray_icon.setToolTip("桌面便签应用")

        self.tray_menu = QMenu()

        # 添加便签
        add_action = QAction("添加便签", self.app)
        add_action.triggered.connect(self.add_note)
        self.tray_menu.addAction(add_action)

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

    def run(self):
        sys.exit(self.app.exec_())

def main():
        manager = StickyNoteManager()
        manager.run()

if __name__ == '__main__':
    main()

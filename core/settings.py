# -*- coding: utf-8 -*-
"""
设置对话框模块

提供主题选择和字体设置界面，使用标签页组织。
"""

import os
import re
from typing import Optional

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QTabWidget, QLabel, QComboBox, QCheckBox,
    QPushButton, QSpinBox, QLineEdit, QTextEdit, QFrame,
    QFontComboBox, QWidget, QProgressBar, QMessageBox, QListWidget,
    QListWidgetItem,
    QScrollArea, QSizePolicy, QApplication, QListView, QStyledItemDelegate,
    QStyleOptionViewItem, QStyle
)
from PyQt5.QtCore import Qt, QObject, QSize, QRectF, QPointF, QTimer
from PyQt5.QtGui import (
    QFont, QKeySequence, QColor, QIcon, QPixmap, QPainter, QPainterPath,
    QPen, QBrush, QFontMetrics
)

from core import get_styles_dir, __version__
from features.shortcuts import (
    get_shortcut_definitions,
    canonical_shortcut,
    validate_shortcut_map,
)
from core.ui_preferences import (
    DEFAULT_SETTINGS_TOOL_ORDER, SETTINGS_TOOL_LABELS,
    SETTINGS_TOOL_ORDER_KEY, normalize_settings_tool_order,
)


# The settings shell is intentionally compact but never allowed to compress a
# form control into its neighbouring row.  Keeping these values in one place
# makes the seven pages use the same rhythm and gives the QSS and geometry
# tests a stable contract.
_SETTINGS_PAGE_MARGINS = (20, 18, 20, 24)
_SETTINGS_PAGE_SPACING = 14
_SETTINGS_GROUP_SPACING = 14
_SETTINGS_FORM_SPACING = 10
_SETTINGS_FIELD_HEIGHT = 34
_SETTINGS_BUTTON_HEIGHT = 36


def _settings_ui_font() -> QFont:
    """Return one stable Windows UI face for all settings chrome."""
    font = QFont('Microsoft YaHei UI', 10)
    font.setStyleHint(QFont.SansSerif)
    font.setWeight(QFont.Normal)
    font.setItalic(False)
    return font


def _standard_settings_field(control, minimum_width: int = 0):
    """Give single-line settings fields one predictable row geometry."""
    control.setMinimumHeight(_SETTINGS_FIELD_HEIGHT)
    control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    if minimum_width:
        control.setMinimumWidth(minimum_width)
    return control


def _standard_settings_button(control, minimum_width: int = 0):
    """Keep action buttons aligned with the field rhythm without fixing width."""
    control.setMinimumHeight(_SETTINGS_BUTTON_HEIGHT)
    if minimum_width:
        control.setMinimumWidth(minimum_width)
    return control


class _UniformFontDelegate(QStyledItemDelegate):
    """Render font family choices with consistent UI typography and row geometry."""

    ROW_HEIGHT = 34
    CONTENT_WIDTH = 300

    def paint(self, painter, option, index):
        item_option = QStyleOptionViewItem(option)
        self.initStyleOption(item_option, index)
        item_option.font = _settings_ui_font()
        item_option.fontMetrics = QFontMetrics(item_option.font)
        item_option.icon = QIcon()
        item_option.decorationSize = QSize(0, 0)
        style = item_option.widget.style() if item_option.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, item_option, painter, item_option.widget)

    def sizeHint(self, option, index):
        return QSize(self.CONTENT_WIDTH, self.ROW_HEIGHT)


class _UniformFontComboBox(QFontComboBox):
    """QFontComboBox with a bounded, readable Windows-style popup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        view = QListView(self)
        view.setUniformItemSizes(True)
        view.setTextElideMode(Qt.ElideRight)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.setView(view)
        self.setItemDelegate(_UniformFontDelegate(self))

    def showPopup(self):
        host_width = self.window().width() if self.window() else self.width()
        popup_width = max(self.width(), min(360, max(280, host_width - 56)))
        super().showPopup()
        self.view().setFixedWidth(popup_width)
        popup = self.view().window()
        if popup:
            frame_width = popup.frameWidth() * 2 if hasattr(popup, 'frameWidth') else 0
            bounded_width = popup_width + frame_width
            popup.setFixedWidth(bounded_width)
            popup.resize(bounded_width, min(popup.height(), 360))


def _mix_color(first: QColor, second: QColor, amount: float) -> QColor:
    """Blend two opaque colours for semantic settings surfaces."""
    amount = max(0.0, min(1.0, amount))
    return QColor(
        round(first.red() * (1 - amount) + second.red() * amount),
        round(first.green() * (1 - amount) + second.green() * amount),
        round(first.blue() * (1 - amount) + second.blue() * amount),
    )


def _relative_luminance(color: QColor) -> float:
    channels = []
    for value in (color.redF(), color.greenF(), color.blueF()):
        channels.append(
            value / 12.92 if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(first: QColor, second: QColor) -> float:
    first_luminance = _relative_luminance(first)
    second_luminance = _relative_luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def _ensure_text_contrast(candidate: QColor, background: QColor,
                          reference: QColor, minimum: float = 4.5) -> QColor:
    """Move secondary text toward the theme text until it is readable."""
    adjusted = QColor(candidate)
    for _ in range(12):
        if _contrast_ratio(adjusted, background) >= minimum:
            return adjusted
        adjusted = _mix_color(adjusted, reference, 0.18)
    return QColor(reference)


def _css_value(css: str, selector: str, prop: str, fallback: str) -> str:
    """Read one simple QSS value without coupling the dialog to note.py."""
    block = re.search(rf'{re.escape(selector)}\s*\{{([^}}]*)\}}', css, re.I | re.S)
    if block:
        value = re.search(
            rf'(?<![-\w]){re.escape(prop)}\s*:\s*([^;]+)',
            block.group(1), re.I
        )
        if value:
            return value.group(1).strip()
    return fallback


def _colour_from_value(value: str, fallback: str) -> QColor:
    """Extract the first QColor-compatible colour from a QSS value."""
    direct = QColor(value.strip())
    if direct.isValid():
        return direct
    match = re.search(r'#[0-9a-fA-F]{3,8}|rgba?\([^)]*\)', value)
    parsed = QColor(match.group(0)) if match else QColor()
    return parsed if parsed.isValid() else QColor(fallback)


def _settings_tokens(css_filename: str) -> dict:
    """Derive a compact settings palette from the selected note theme."""
    css = ''
    css_path = os.path.join(get_styles_dir(), css_filename or '')
    try:
        with open(css_path, 'r', encoding='utf-8') as theme_file:
            css = theme_file.read()
    except (OSError, UnicodeError):
        pass

    canvas = _colour_from_value(
        _css_value(css, 'StickyNote', 'background-color', '#F7F8FA'), '#F7F8FA'
    )
    text = _colour_from_value(
        _css_value(css, 'StickyNote', 'color', '#1F2937'), '#1F2937'
    )
    field = _colour_from_value(
        _css_value(css, 'QLineEdit', 'background-color', canvas.name()),
        canvas.name()
    )
    accent = _colour_from_value(
        _css_value(css, 'QPushButton', 'background-color', '#2F6FED'), '#2F6FED'
    )
    border = _colour_from_value(
        _css_value(css, 'QLineEdit', 'border', accent.name()), accent.name()
    )
    luminance = (0.2126 * canvas.red() + 0.7152 * canvas.green() + 0.0722 * canvas.blue()) / 255
    dark = luminance < 0.48
    high_contrast = 'high_contrast' in (css_filename or '').lower()
    neutral = QColor('#FFFFFF' if dark else '#18212F')

    # A button fill can be very close to the canvas (classic themes).  Keep the
    # user's hue, but move it far enough to remain a visible active indicator.
    if abs((0.2126 * accent.red() + 0.7152 * accent.green() + 0.0722 * accent.blue()) / 255 - luminance) < 0.18:
        accent = _mix_color(accent, neutral, 0.48)
    if high_contrast:
        accent = QColor('#FFFF00')
        border = QColor('#FFFF00')

    surface = _mix_color(canvas, QColor('#FFFFFF' if dark else '#000000'), 0.07 if dark else 0.025)
    surface_alt = _mix_color(canvas, QColor('#FFFFFF' if dark else '#000000'), 0.13 if dark else 0.055)
    muted = _ensure_text_contrast(
        _mix_color(text, canvas, 0.38 if not high_contrast else 0.12),
        surface, text,
    )
    black = QColor('#000000')
    white = QColor('#FFFFFF')
    accent_text = (
        black if _contrast_ratio(black, accent) >= _contrast_ratio(white, accent)
        else white
    )
    danger = QColor('#FF8A80' if dark else '#B42318')
    warning = QColor('#FFD166' if dark else '#7A4B00')
    return {
        'canvas': canvas.name(), 'surface': surface.name(),
        'surface_alt': surface_alt.name(), 'field': field.name(),
        'text': text.name(), 'muted': muted.name(), 'border': border.name(),
        'accent': accent.name(), 'accent_text': accent_text.name(),
        'danger': danger.name(), 'warning': warning.name(),
        'dark': dark, 'high_contrast': high_contrast,
    }


def _settings_icon(kind: str, color: str, size: int = 36) -> QIcon:
    """Draw a small, dependency-free outline icon family for the settings UI."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color), max(2.0, size / 18.0), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    c = size / 2
    u = size / 8

    if kind == 'theme':
        painter.drawEllipse(QPointF(c, c), u * 2.6, u * 2.6)
        painter.drawEllipse(QPointF(c - u, c - u), u * .55, u * .55)
        painter.drawEllipse(QPointF(c + u, c - u * .55), u * .55, u * .55)
        painter.drawEllipse(QPointF(c, c + u), u * .55, u * .55)
    elif kind == 'font':
        painter.drawLine(QPointF(c - u * 2.6, c - u * 2.3), QPointF(c + u * 1.2, c - u * 2.3))
        painter.drawLine(QPointF(c - u * .7, c - u * 2.3), QPointF(c - u * .7, c + u * 2.3))
        painter.drawLine(QPointF(c - u * 1.8, c + u * 2.3), QPointF(c + u * .4, c + u * 2.3))
        painter.drawLine(QPointF(c + u * .9, c), QPointF(c + u * 2.7, c))
        painter.drawLine(QPointF(c + u * 1.8, c), QPointF(c + u * 1.8, c + u * 2.3))
    elif kind == 'update':
        path = QPainterPath()
        path.arcMoveTo(QRectF(c-u*2.6, c-u*2.6, u*5.2, u*5.2), 38)
        path.arcTo(QRectF(c-u*2.6, c-u*2.6, u*5.2, u*5.2), 38, 274)
        painter.drawPath(path)
        painter.drawLine(QPointF(c+u*2.5, c-u*.7), QPointF(c+u*2.6, c-u*2.3))
        painter.drawLine(QPointF(c+u*2.5, c-u*.7), QPointF(c+u*.9, c-u*.9))
    elif kind == 'security':
        shield = QPainterPath()
        shield.moveTo(c, c-u*2.8)
        shield.lineTo(c+u*2.5, c-u*1.8)
        shield.lineTo(c+u*2.1, c+u*.9)
        shield.quadTo(c+u*1.2, c+u*2.6, c, c+u*3)
        shield.quadTo(c-u*1.2, c+u*2.6, c-u*2.1, c+u*.9)
        shield.lineTo(c-u*2.5, c-u*1.8)
        shield.closeSubpath()
        painter.drawPath(shield)
        painter.drawLine(QPointF(c-u*.7, c), QPointF(c-u*.1, c+u*.7))
        painter.drawLine(QPointF(c-u*.1, c+u*.7), QPointF(c+u*1.1, c-u*.7))
    elif kind == 'sync':
        cloud = QPainterPath()
        cloud.moveTo(c-u*2.8, c+u*1.3)
        cloud.cubicTo(c-u*3.2, c-u*.2, c-u*2.1, c-u*1.2, c-u*.9, c-u*1.1)
        cloud.cubicTo(c-u*.5, c-u*3, c+u*2.3, c-u*2.9, c+u*2.5, c-u*.8)
        cloud.cubicTo(c+u*3.7, c-u*.3, c+u*3.3, c+u*1.5, c+u*2.1, c+u*1.5)
        cloud.lineTo(c-u*2.1, c+u*1.5)
        painter.drawPath(cloud)
        painter.drawLine(QPointF(c-u*.7, c+u*2.5), QPointF(c+u*.7, c+u*2.5))
    elif kind == 'plugins':
        puzzle = QPainterPath()
        puzzle.moveTo(c-u*2.6, c-u*2.1)
        puzzle.lineTo(c-u*.7, c-u*2.1)
        puzzle.cubicTo(c-u*.9, c-u*3.5, c+u*1.1, c-u*3.5, c+u*.9, c-u*2.1)
        puzzle.lineTo(c+u*2.6, c-u*2.1)
        puzzle.lineTo(c+u*2.6, c-u*.4)
        puzzle.cubicTo(c+u*4, c-u*.6, c+u*4, c+u*1.4, c+u*2.6, c+u*1.2)
        puzzle.lineTo(c+u*2.6, c+u*2.6)
        puzzle.lineTo(c-u*2.6, c+u*2.6)
        puzzle.closeSubpath()
        painter.drawPath(puzzle)
    elif kind == 'shortcuts':
        painter.drawRoundedRect(QRectF(c-u*3, c-u*2.3, u*6, u*4.6), u*.6, u*.6)
        for row_y in (-u*.8, u*.4):
            for col_x in (-u*1.8, -u*.6, u*.6, u*1.8):
                painter.drawPoint(QPointF(c+col_x, c+row_y))
        painter.drawLine(QPointF(c-u*1.4, c+u*1.5), QPointF(c+u*1.4, c+u*1.5))
    else:  # dialog/window icon: three aligned controls
        for offset in (-u*1.6, 0, u*1.6):
            painter.drawLine(QPointF(c-u*2.6, c+offset), QPointF(c+u*2.6, c+offset))
        painter.drawEllipse(QPointF(c-u*.9, c-u*1.6), u*.45, u*.45)
        painter.drawEllipse(QPointF(c+u*1.1, c), u*.45, u*.45)
        painter.drawEllipse(QPointF(c-u*.2, c+u*1.6), u*.45, u*.45)
    painter.end()
    return QIcon(pixmap)


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
        self.setFont(_settings_ui_font())
        self.initUI()
        self._apply_current_theme()

    def initUI(self):
        self.setWindowTitle('\u8bbe\u7f6e')
        self.setObjectName('settingsDialog')
        self.setWindowIcon(_settings_icon('settings', '#2F6FED', 40))
        self.setMinimumSize(760, 580)
        self.resize(820, 640)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName('settingsHeader')
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 16, 24, 15)
        header_layout.setSpacing(12)
        self.settings_header_icon = QLabel()
        self.settings_header_icon.setObjectName('settingsHeaderIcon')
        self.settings_header_icon.setFixedSize(32, 32)
        self.settings_header_icon.setAlignment(Qt.AlignCenter)
        self.settings_header_icon.setFocusPolicy(Qt.NoFocus)
        self.settings_header_icon.setPixmap(
            _settings_icon('settings', '#2F6FED', 32).pixmap(28, 28)
        )
        title_label = QLabel('偏好设置')
        title_label.setObjectName('settingsTitle')
        title_label.setAccessibleName('偏好设置标题')
        subtitle_label = QLabel('统一管理便签外观、更新、安全、同步与快捷操作')
        subtitle_label.setObjectName('settingsSubtitle')
        subtitle_label.setProperty('settingsRole', 'muted')
        title_stack = QVBoxLayout()
        title_stack.setContentsMargins(0, 0, 0, 0)
        title_stack.setSpacing(3)
        title_stack.addWidget(title_label)
        title_stack.addWidget(subtitle_label)
        header_layout.addWidget(self.settings_header_icon, 0, Qt.AlignVCenter)
        header_layout.addLayout(title_stack, 1)
        main_layout.addWidget(header)

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName('settingsTabs')
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setMovable(False)
        self.tab_widget.setUsesScrollButtons(True)
        self.tab_widget.tabBar().setExpanding(False)
        self.tab_widget.setAccessibleName('设置分类')
        self.tab_widget.tabBar().setAccessibleName('设置分类标签')

        theme_tab = QWidget()
        self.setup_theme_tab(theme_tab)
        self._add_tab(theme_tab, "主题", 'theme', "主题设置")

        font_tab = QWidget()
        self.setup_font_tab(font_tab)
        self._add_tab(font_tab, "字体", 'font', "字体设置", scrollable=True)

        update_tab = QWidget()
        self.setup_update_tab(update_tab)
        self._add_tab(update_tab, "更新", 'update', "更新设置", scrollable=True)

        security_tab = QWidget()
        self.setup_security_tab(security_tab)
        self._add_tab(security_tab, "安全", 'security', "安全设置", scrollable=True)

        sync_tab = QWidget()
        self.setup_sync_tab(sync_tab)
        self._add_tab(sync_tab, "云同步", 'sync', "云同步设置", scrollable=True)

        plugins_tab = QWidget()
        self.setup_plugins_tab(plugins_tab)
        self._add_tab(plugins_tab, "插件", 'plugins', "插件设置")

        shortcuts_tab = QWidget()
        self.setup_shortcuts_tab(shortcuts_tab)
        self._add_tab(shortcuts_tab, "快捷键", 'shortcuts', "快捷键设置")

        main_layout.addWidget(self.tab_widget, 1)

        author_label = QLabel(f"v{__version__} | By MaWenshui")
        author_label.setObjectName('settingsVersion')
        author_label.setAccessibleName(f'应用版本 {__version__}')
        author_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(author_label)

        self._configure_accessibility()

    def _add_tab(self, page: QWidget, label: str, icon_kind: str, accessible_label=None,
                 scrollable: bool = False):
        """Register one stable settings page without changing its behaviour."""
        accessible_label = accessible_label or label
        tab_page = page
        if scrollable:
            page.setObjectName(f'{icon_kind}SettingsContent')
            page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            page.setMinimumWidth(0)
            scroll = QScrollArea()
            scroll.setObjectName(f'{icon_kind}SettingsPage')
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setWidget(page)
            # Keep the viewport in the keyboard traversal order.  Wheel/touch
            # scrolling still works, while a keyboard user can focus the
            # page and use PageUp/PageDown when the content exceeds the shell.
            scroll.setFocusPolicy(Qt.StrongFocus)
            scroll.setAccessibleName(f'{accessible_label}内容滚动区域')
            scroll.setProperty('settingsScroll', True)
            tab_page = scroll
            setattr(self, f'{icon_kind}_settings_scroll', scroll)
        else:
            page.setObjectName(f'{icon_kind}SettingsPage')
        tab_page.setProperty('settingsPage', True)
        tab_page.setAccessibleName(accessible_label)
        index = self.tab_widget.addTab(tab_page, label)
        self.tab_widget.setTabToolTip(index, accessible_label)
        self.tab_widget.setTabWhatsThis(index, f'打开{accessible_label}')
        tab_page.setProperty('settingsIconKind', icon_kind)

    def _apply_current_theme(self, css_filename=None):
        """Apply theme-aware dialog chrome and refresh tab icon contrast."""
        try:
            from features.theme_helper import apply_dialog_theme, get_current_theme_css
            css_filename = css_filename or get_current_theme_css(self.manager)
            apply_dialog_theme(self, css_filename)
        except Exception:
            css_filename = css_filename or 'soft_yellow.css'
        self._apply_product_style(css_filename)

    def _apply_product_style(self, css_filename: str):
        tokens = _settings_tokens(css_filename)
        self._settings_theme_tokens = tokens
        high_contrast_border = 2 if tokens['high_contrast'] else 1
        arrow_variant = (
            'contrast' if tokens['high_contrast']
            else ('light' if tokens['dark'] else 'dark')
        )
        arrow_path = os.path.join(
            get_styles_dir(), 'icons', f'chevron-down-{arrow_variant}.svg'
        ).replace('\\', '/')
        up_arrow_path = os.path.join(
            get_styles_dir(), 'icons', f'chevron-up-{arrow_variant}.svg'
        ).replace('\\', '/')
        check_variant = (
            'light' if QColor(tokens['accent_text']).lightness() >= 128 else 'dark'
        )
        check_path = os.path.join(
            get_styles_dir(), 'icons', f'check-{check_variant}.svg'
        ).replace('\\', '/')
        ui_font_family = _settings_ui_font().family()
        product_style = f"""
            QDialog#settingsDialog {{
                background: {tokens['canvas']}; color: {tokens['text']};
                font-family: "{ui_font_family}";
            }}
            QFrame#settingsHeader {{
                background: {tokens['surface']};
                border: none; border-bottom: {high_contrast_border}px solid {tokens['border']};
            }}
            QLabel#settingsTitle {{
                color: {tokens['text']}; background: transparent;
                font-family: "{ui_font_family}"; font-size: 22px; font-weight: bold;
            }}
            QLabel#settingsHeaderIcon {{ background: transparent; }}
            QLabel#settingsSubtitle, QLabel[settingsRole="muted"], QLabel#settingsVersion {{
                color: {tokens['muted']}; background: transparent;
                font-family: "{ui_font_family}";
            }}
            QLabel[settingsRole="fieldLabel"] {{
                color: {tokens['text']}; background: transparent;
                font-family: "{ui_font_family}"; font-size: 13px;
                font-weight: bold; min-height: 20px;
            }}
            QLabel#updateStatus[status="working"] {{ color: {tokens['accent']}; font-weight: bold; }}
            QLabel#fontPreview {{
                color: {tokens['text']}; background: {tokens['surface_alt']};
                border: {high_contrast_border}px solid {tokens['border']};
                border-radius: 9px; padding: 20px;
            }}
            QLabel#settingsVersion {{
                padding: 9px 0 11px 0; font-size: 12px;
                border-top: {high_contrast_border}px solid {tokens['border']};
            }}
            QTabWidget#settingsTabs {{ background: {tokens['canvas']}; }}
            QTabBar {{
                background: {tokens['surface']};
                border-bottom: {high_contrast_border}px solid {tokens['border']};
                padding-left: 14px;
            }}
            QTabWidget#settingsTabs::pane {{
                background: {tokens['surface']};
                border: {high_contrast_border}px solid {tokens['border']};
                border-radius: 12px; margin: 0 14px 8px 14px;
            }}
            QTabBar::tab {{
                background: {tokens['surface_alt']}; color: {tokens['muted']};
                min-height: 38px; min-width: 56px;
                padding: 0 9px; margin: 6px 3px 7px 3px;
                border: {high_contrast_border}px solid {tokens['border']};
                border-radius: 7px; font-family: "{ui_font_family}";
                font-size: 13px; font-weight: normal;
            }}
            QTabBar::tab:hover {{
                color: {tokens['text']}; background: {tokens['field']};
                border-color: {tokens['accent']};
            }}
            QTabBar::tab:selected {{
                color: {tokens['accent']}; background: {tokens['surface']};
                border: 2px solid {tokens['accent']}; font-weight: bold;
            }}
            QTabBar::tab:focus {{ border: 2px solid {tokens['accent']}; }}
            QWidget[settingsPage="true"] {{ background: {tokens['surface']}; }}
            QGroupBox {{
                color: {tokens['text']}; background: {tokens['surface']};
                border: {high_contrast_border}px solid {tokens['border']};
                border-radius: 10px; margin-top: 14px; padding: 18px 14px 14px 14px;
                font-family: "{ui_font_family}"; font-size: 14px;
                font-weight: bold; font-style: normal;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 12px; padding: 0 6px;
                color: {tokens['text']}; background: {tokens['surface']};
            }}
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QFontComboBox, QSpinBox {{
                background: {tokens['field']}; color: {tokens['text']};
                border: {high_contrast_border}px solid {tokens['border']};
                border-radius: 7px; min-height: {_SETTINGS_FIELD_HEIGHT}px; padding: 3px 9px;
                font-family: "{ui_font_family}"; font-size: 14px;
                font-weight: normal; font-style: normal;
                selection-background-color: {tokens['accent']};
                selection-color: {tokens['accent_text']};
            }}
            QTextEdit {{ min-height: 88px; }}
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QFontComboBox:focus, QSpinBox:focus {{
                border: 2px solid {tokens['accent']};
            }}
            QComboBox::drop-down, QFontComboBox::drop-down {{
                subcontrol-origin: padding; subcontrol-position: top right;
                width: 30px; border: none; border-left: 1px solid {tokens['border']};
                background: {tokens['surface_alt']};
                border-top-right-radius: 6px; border-bottom-right-radius: 6px;
            }}
            QComboBox::down-arrow, QFontComboBox::down-arrow {{
                image: url("{arrow_path}"); width: 12px; height: 12px;
            }}
            QSpinBox {{ padding-right: 34px; }}
            QSpinBox::up-button, QSpinBox::down-button {{
                subcontrol-origin: border; width: 30px;
                background: {tokens['surface_alt']};
                border: none; border-left: 1px solid {tokens['border']};
            }}
            QSpinBox::up-button {{
                subcontrol-position: top right; border-bottom: 1px solid {tokens['border']};
                border-top-right-radius: 6px;
            }}
            QSpinBox::down-button {{
                subcontrol-position: bottom right; border-bottom-right-radius: 6px;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: {tokens['field']};
            }}
            QSpinBox::up-arrow {{
                image: url("{up_arrow_path}"); width: 10px; height: 8px;
            }}
            QSpinBox::down-arrow {{
                image: url("{arrow_path}"); width: 10px; height: 8px;
            }}
            QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {{
                background: {tokens['surface']}; color: {tokens['text']};
                border: 1px solid {tokens['border']};
                border-radius: 7px; padding: 4px; outline: none;
                font-family: "{ui_font_family}"; font-size: 14px;
                font-weight: normal; font-style: normal;
                selection-background-color: {tokens['accent']};
                selection-color: {tokens['accent_text']};
            }}
            QListWidget#settingsToolOrderList {{
                background: {tokens['field']}; color: {tokens['text']};
                border: {high_contrast_border}px solid {tokens['border']};
                border-radius: 7px; padding: 5px; outline: none;
                font-family: "{ui_font_family}"; font-size: 14px;
            }}
            QListWidget#settingsToolOrderList::item {{
                min-height: 30px; padding: 2px 8px; border-radius: 5px;
            }}
            QListWidget#settingsToolOrderList::item:hover {{
                background: {tokens['surface_alt']};
            }}
            QListWidget#settingsToolOrderList::item:selected {{
                background: {tokens['accent']}; color: {tokens['accent_text']};
            }}
            QListWidget#settingsToolOrderList:focus {{
                border: 2px solid {tokens['accent']};
            }}
            QFrame#toolOrderPreview {{
                background: {tokens['surface_alt']};
                border: {high_contrast_border}px solid {tokens['border']};
                border-radius: 9px;
            }}
            QFrame#toolOrderPreview QLabel[previewChip="true"] {{
                background: {tokens['field']}; color: {tokens['text']};
                border: 1px solid {tokens['border']}; border-radius: 6px;
                padding: 2px 8px; font-size: 13px;
            }}
            QLabel[shortcutStatusKind="success"] {{ color: {tokens['text']}; }}
            QLabel[shortcutStatusKind="warning"] {{ color: {tokens['warning']}; }}
            QLabel[shortcutStatusKind="error"] {{ color: {tokens['danger']}; font-weight: bold; }}
            QPushButton {{
                background: {tokens['surface_alt']}; color: {tokens['text']};
                border: {high_contrast_border}px solid {tokens['border']};
                border-radius: 7px; min-height: {_SETTINGS_BUTTON_HEIGHT}px; padding: 2px 14px;
                font-family: "{ui_font_family}"; font-size: 14px;
                font-weight: normal; font-style: normal;
            }}
            QPushButton:hover {{
                border-color: {tokens['accent']}; background: {tokens['field']};
            }}
            QPushButton:pressed {{ background: {tokens['border']}; }}
            QPushButton:focus {{ border: 2px solid {tokens['accent']}; }}
            QPushButton[settingsRole="primary"] {{
                background: {tokens['accent']}; color: {tokens['accent_text']};
                border-color: {tokens['accent']}; font-weight: bold;
            }}
            QPushButton[settingsRole="danger"] {{
                background: transparent; color: {tokens['danger']};
                border-color: {tokens['danger']};
            }}
            QPushButton:disabled {{
                color: {tokens['muted']}; background: {tokens['surface_alt']};
                border-color: {tokens['border']};
            }}
            QCheckBox {{
                color: {tokens['text']}; spacing: 8px; min-height: {_SETTINGS_FIELD_HEIGHT}px;
                font-family: "{ui_font_family}"; font-size: 14px;
                font-weight: normal; font-style: normal;
            }}
            QCheckBox:focus {{ color: {tokens['accent']}; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px; background: {tokens['field']};
                border: {high_contrast_border}px solid {tokens['border']};
                border-radius: 4px;
            }}
            QCheckBox::indicator:hover {{ border-color: {tokens['accent']}; }}
            QCheckBox::indicator:checked {{
                background: {tokens['accent']}; border-color: {tokens['accent']};
                image: url("{check_path}");
            }}
            QProgressBar {{
                background: {tokens['surface_alt']}; border: none;
                border-radius: 4px; min-height: 8px;
            }}
            QProgressBar::chunk {{ background: {tokens['accent']}; border-radius: 4px; }}
            QScrollArea, QScrollArea > QWidget > QWidget {{
                background: transparent; border: none;
            }}
            QScrollArea:focus {{
                border: 2px solid {tokens['accent']}; border-radius: 8px;
            }}
            QScrollBar:vertical {{
                background: {tokens['surface_alt']}; width: 10px;
                margin: 2px; border: none; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {tokens['border']}; min-height: 36px;
                border: none; border-radius: 3px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {tokens['accent']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            QLabel[shortcutBadge="true"] {{
                background: {tokens['surface_alt']}; color: {tokens['text']};
                border: 1px solid {tokens['border']}; border-radius: 6px;
                padding: 5px 9px; font-family: Consolas, monospace;
            }}
            QFrame#themePreview {{
                border: 1px solid {tokens['border']}; border-radius: 12px;
            }}
        """
        # Retain the base theme helper rules for native widgets, then make the
        # product-specific selectors the final authority for this dialog.
        # Qt 5's Windows style-sheet parser can discard the appended rule set
        # when a large f-string ends in indentation-only whitespace.  Normalise
        # the boundary so the product selectors are reliably polished.
        final_style = (self.styleSheet() + product_style).strip()
        self._resolved_product_stylesheet = final_style
        self.setStyleSheet(final_style)
        # The Windows Qt 5 backend finalises the native dialog style after the
        # constructor returns.  Re-applying on the next event-loop turn makes
        # the child-specific rules (title hierarchy, cards, active tab) win
        # consistently instead of leaving only the base dialog theme visible.
        QTimer.singleShot(0, self._repolish_product_style)
        icon_color = tokens['accent']
        if hasattr(self, 'settings_header_icon'):
            self.settings_header_icon.setPixmap(
                _settings_icon('settings', icon_color, 32).pixmap(28, 28)
            )
        for index in range(self.tab_widget.count()):
            page = self.tab_widget.widget(index)
            kind = page.property('settingsIconKind') or 'settings'
            self.tab_widget.setTabIcon(index, _settings_icon(str(kind), icon_color, 32))
            self.tab_widget.setIconSize(QSize(16, 16))
        self.setWindowIcon(_settings_icon('settings', icon_color, 40))

    def _repolish_product_style(self):
        final_style = getattr(self, '_resolved_product_stylesheet', '')
        if not final_style:
            return
        self.setStyleSheet(final_style + '\n')

    def _configure_accessibility(self):
        controls = {
            'theme_combo': '默认便签主题',
            'font_family_combo': '默认字体',
            'font_size_spinbox': '默认字号',
            'font_bold_checkbox': '默认使用粗体',
            'font_italic_checkbox': '默认使用斜体',
            'auto_update_checkbox': '启动后自动检查更新',
            'check_update_btn': '立即检查更新',
            'cancel_check_btn': '取消更新检查',
            'master_pwd_checkbox': '启用主密码',
            'set_master_pwd_btn': '设置或修改主密码',
            'sync_enabled_cb': '启用云同步',
            'sync_provider_combo': '同步提供商',
            'webdav_url': 'WebDAV 服务地址',
            'webdav_user': 'WebDAV 用户名',
            'webdav_pwd': 'WebDAV 密码',
            'webdav_path': 'WebDAV 远程路径',
            'auto_sync_cb': '启用自动同步',
            'sync_interval_spin': '自动同步间隔',
            'plugins_enabled_cb': '启用插件系统',
            'tool_order_up_btn': '将工具组向左移动',
            'tool_order_down_btn': '将工具组向右移动',
            'tool_order_reset_btn': '恢复底部工具推荐顺序',
            'reset_font_btn': '重置为默认字体',
            'save_webdav_btn': '保存 WebDAV 配置',
            'apply_recommended_btn': '应用推荐快捷键组合',
            'save_shortcuts_btn': '保存快捷键',
        }
        for name, accessible_name in controls.items():
            control = getattr(self, name, None)
            if control is not None:
                if not control.objectName():
                    control.setObjectName(name)
                control.setAccessibleName(accessible_name)
                control.setFocusPolicy(Qt.StrongFocus)

    def setup_theme_tab(self, tab_widget):
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        theme_scroll = QScrollArea()
        theme_scroll.setObjectName('themeSettingsScroll')
        theme_scroll.setWidgetResizable(True)
        theme_scroll.setFrameShape(QFrame.NoFrame)
        theme_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.theme_scroll = theme_scroll
        content = QWidget()
        content.setProperty('settingsPage', True)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(*_SETTINGS_PAGE_MARGINS)
        layout.setSpacing(_SETTINGS_GROUP_SPACING)

        # 主题选择区域
        theme_group = QGroupBox("\u4e3b\u9898\u9009\u62e9")
        theme_layout = QFormLayout()
        theme_layout.setHorizontalSpacing(14)
        theme_layout.setVerticalSpacing(_SETTINGS_FORM_SPACING)

        self.theme_label = QLabel("\u9009\u62e9\u4fbf\u7b7e\u9ed8\u8ba4\u4e3b\u9898:")
        self.theme_combo = QComboBox()
        _standard_settings_field(self.theme_combo, 260)
        self.load_themes()

        current_theme_css = self.manager.get_default_theme_css()
        current_theme_name = self.manager.get_theme_name_by_css(current_theme_css)
        if current_theme_name:
            index = self.theme_combo.findText(current_theme_name)
            if index != -1:
                self.theme_combo.setCurrentIndex(index)
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)

        theme_layout.addRow(self.theme_label, self.theme_combo)
        theme_hint = QLabel('选择后会立即应用到已有便签，新建便签也会沿用该主题。')
        theme_hint.setProperty('settingsRole', 'muted')
        theme_hint.setWordWrap(True)
        theme_layout.addRow('', theme_hint)
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)

        # Daily control order is part of the theme-facing note chrome. Place
        # it before the decorative theme preview so it is immediately useful.
        self._setup_tool_order_editor(layout)

        # 主题预览区域
        preview_group = QGroupBox("\u4e3b\u9898\u9884\u89c8")
        self.preview_group = preview_group
        preview_layout = QVBoxLayout()

        self.preview_note = QFrame()
        self.preview_note.setObjectName('themePreview')
        self.preview_note.setMinimumSize(340, 190)
        self.preview_note.setMaximumSize(520, 230)
        self.preview_note.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_note.setFrameStyle(QFrame.StyledPanel)

        preview_note_layout = QVBoxLayout()
        self.preview_title = QLineEdit("\u9884\u89c8\u6807\u9898")
        self.preview_title.setObjectName('themePreviewTitle')
        self.preview_title.setReadOnly(True)
        self.preview_title.setFocusPolicy(Qt.NoFocus)
        preview_note_layout.addWidget(self.preview_title)

        self.preview_content = QTextEdit()
        self.preview_content.setObjectName('themePreviewContent')
        self.preview_content.setPlainText("\u8fd9\u662f\u4e3b\u9898\u9884\u89c8\u5185\u5bb9\n\u53ef\u4ee5\u770b\u5230\u5f53\u524d\u4e3b\u9898\u7684\u6837\u5f0f\u6548\u679c")
        self.preview_content.setReadOnly(True)
        self.preview_content.setFocusPolicy(Qt.NoFocus)
        preview_note_layout.addWidget(self.preview_content)

        preview_footer = QHBoxLayout()
        preview_footer.setSpacing(6)
        self.preview_footer_chips = []
        for label_text in ('Aa', '对齐', '更多'):
            preview_chip = QLabel(label_text)
            preview_chip.setAlignment(Qt.AlignCenter)
            preview_chip.setProperty('previewChip', True)
            preview_chip.setMinimumSize(44, 24)
            self.preview_footer_chips.append(preview_chip)
            preview_footer.addWidget(preview_chip)
        preview_footer.addStretch()
        preview_note_layout.addLayout(preview_footer)

        self.preview_note.setLayout(preview_note_layout)
        preview_layout.addWidget(self.preview_note, 0, Qt.AlignHCenter)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        layout.addStretch()
        theme_scroll.setWidget(content)
        outer_layout.addWidget(theme_scroll)
        self.update_theme_preview()
        tab_widget.setLayout(outer_layout)

    def _current_settings_tool_order(self):
        getter = getattr(self.manager, 'get_settings_tool_order', None)
        if callable(getter):
            return normalize_settings_tool_order(getter())
        config = getattr(self.manager, 'config', None)
        if config is not None and hasattr(config, 'get'):
            return normalize_settings_tool_order(
                config.get(SETTINGS_TOOL_ORDER_KEY, None)
            )
        return list(DEFAULT_SETTINGS_TOOL_ORDER)

    def _setup_tool_order_editor(self, parent_layout):
        """Build a reorderable list whose preview matches the note settings rail."""
        group = QGroupBox('底部常用工具顺序')
        group.setAccessibleName('底部常用工具顺序')
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        hint = QLabel('列表从上到下对应便签底部从左到右。拖动项目或使用按钮调整，已打开便签会立即预览。')
        hint.setProperty('settingsRole', 'muted')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        editor_row = QHBoxLayout()
        editor_row.setSpacing(10)
        self.settings_tool_order_list = QListWidget()
        self.settings_tool_order_list.setObjectName('settingsToolOrderList')
        self.settings_tool_order_list.setAccessibleName('便签底部工具展示顺序')
        self.settings_tool_order_list.setDragDropMode(QListWidget.InternalMove)
        self.settings_tool_order_list.setDefaultDropAction(Qt.MoveAction)
        self.settings_tool_order_list.setSelectionMode(QListWidget.SingleSelection)
        self.settings_tool_order_list.setMinimumHeight(154)
        self.settings_tool_order_list.setMaximumHeight(170)
        for key in self._current_settings_tool_order():
            item = QListWidgetItem(SETTINGS_TOOL_LABELS[key])
            item.setData(Qt.UserRole, key)
            item.setToolTip(f'便签底部工具组：{SETTINGS_TOOL_LABELS[key]}')
            self.settings_tool_order_list.addItem(item)
        self.settings_tool_order_list.setCurrentRow(0)
        editor_row.addWidget(self.settings_tool_order_list, 1)

        actions = QVBoxLayout()
        actions.setSpacing(8)
        self.tool_order_up_btn = QPushButton('上移')
        _standard_settings_button(self.tool_order_up_btn, 76)
        self.tool_order_up_btn.setAccessibleName('将工具组向左移动')
        self.tool_order_up_btn.clicked.connect(lambda: self._move_tool_order(-1))
        actions.addWidget(self.tool_order_up_btn)
        self.tool_order_down_btn = QPushButton('下移')
        _standard_settings_button(self.tool_order_down_btn, 76)
        self.tool_order_down_btn.setAccessibleName('将工具组向右移动')
        self.tool_order_down_btn.clicked.connect(lambda: self._move_tool_order(1))
        actions.addWidget(self.tool_order_down_btn)
        self.tool_order_reset_btn = QPushButton('恢复推荐顺序')
        _standard_settings_button(self.tool_order_reset_btn, 112)
        self.tool_order_reset_btn.setAccessibleName('恢复底部工具推荐顺序')
        self.tool_order_reset_btn.clicked.connect(self._reset_tool_order)
        actions.addWidget(self.tool_order_reset_btn)
        actions.addStretch()
        editor_row.addLayout(actions)
        layout.addLayout(editor_row)

        preview_label = QLabel('实时预览')
        preview_label.setProperty('settingsRole', 'muted')
        layout.addWidget(preview_label)
        self.tool_order_preview = QFrame()
        self.tool_order_preview.setObjectName('toolOrderPreview')
        self.tool_order_preview.setAccessibleName('便签底部工具顺序实时预览')
        self.tool_order_preview_layout = QHBoxLayout(self.tool_order_preview)
        self.tool_order_preview_layout.setContentsMargins(8, 6, 8, 6)
        self.tool_order_preview_layout.setSpacing(6)
        layout.addWidget(self.tool_order_preview)

        self.settings_tool_order_list.model().rowsMoved.connect(
            lambda *args: self._commit_tool_order()
        )
        self.settings_tool_order_list.currentRowChanged.connect(
            self._update_tool_order_buttons
        )
        self._update_tool_order_preview()
        self._update_tool_order_buttons(0)
        parent_layout.addWidget(group)

    def _tool_order_from_list(self):
        return normalize_settings_tool_order([
            self.settings_tool_order_list.item(index).data(Qt.UserRole)
            for index in range(self.settings_tool_order_list.count())
        ])

    def _update_tool_order_buttons(self, row):
        count = self.settings_tool_order_list.count()
        self.tool_order_up_btn.setEnabled(row > 0)
        self.tool_order_down_btn.setEnabled(0 <= row < count - 1)

    def _move_tool_order(self, offset):
        row = self.settings_tool_order_list.currentRow()
        target = row + int(offset)
        if row < 0 or target < 0 or target >= self.settings_tool_order_list.count():
            return
        item = self.settings_tool_order_list.takeItem(row)
        self.settings_tool_order_list.insertItem(target, item)
        self.settings_tool_order_list.setCurrentRow(target)
        self._commit_tool_order()

    def _reset_tool_order(self):
        self.settings_tool_order_list.clear()
        for key in DEFAULT_SETTINGS_TOOL_ORDER:
            item = QListWidgetItem(SETTINGS_TOOL_LABELS[key])
            item.setData(Qt.UserRole, key)
            self.settings_tool_order_list.addItem(item)
        self.settings_tool_order_list.setCurrentRow(0)
        self._commit_tool_order()

    def _commit_tool_order(self):
        order = self._tool_order_from_list()
        setter = getattr(self.manager, 'set_settings_tool_order', None)
        if callable(setter):
            order = normalize_settings_tool_order(setter(order))
        else:
            config = getattr(self.manager, 'config', None)
            if config is not None and hasattr(config, 'set'):
                config.set(SETTINGS_TOOL_ORDER_KEY, order)
        self._update_tool_order_preview(order)
        self._update_tool_order_buttons(self.settings_tool_order_list.currentRow())

    def _update_tool_order_preview(self, order=None):
        if not hasattr(self, 'tool_order_preview_layout'):
            return
        order = normalize_settings_tool_order(order or self._tool_order_from_list())
        while self.tool_order_preview_layout.count():
            item = self.tool_order_preview_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for key in order:
            chip = QLabel(SETTINGS_TOOL_LABELS[key])
            chip.setAlignment(Qt.AlignCenter)
            chip.setProperty('previewChip', True)
            chip.setAccessibleName(f'预览工具组：{SETTINGS_TOOL_LABELS[key]}')
            chip.setMinimumHeight(28)
            self.tool_order_preview_layout.addWidget(chip)
        self.tool_order_preview_layout.addStretch()

    def setup_font_tab(self, tab_widget):
        layout = QVBoxLayout()
        layout.setContentsMargins(*_SETTINGS_PAGE_MARGINS)
        layout.setSpacing(_SETTINGS_GROUP_SPACING)

        font_group = QGroupBox("\u5b57\u4f53\u8bbe\u7f6e")
        font_layout = QFormLayout()
        font_layout.setHorizontalSpacing(14)
        font_layout.setVerticalSpacing(_SETTINGS_FORM_SPACING)

        self.font_family_combo = _UniformFontComboBox()
        _standard_settings_field(self.font_family_combo, 220)
        current_font = self.manager.get_default_font()
        if current_font:
            self.font_family_combo.setCurrentFont(QFont(current_font['family']))
        self.font_family_combo.currentFontChanged.connect(self.on_font_changed)
        font_layout.addRow("\u5b57\u4f53\u65cf:", self.font_family_combo)

        self.font_size_spinbox = QSpinBox()
        _standard_settings_field(self.font_size_spinbox, 110)
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
        self.font_preview_label.setObjectName('fontPreview')
        self.font_preview_label.setAlignment(Qt.AlignCenter)
        self.font_preview_label.setMinimumHeight(100)
        font_preview_layout.addWidget(self.font_preview_label)
        font_preview_group.setLayout(font_preview_layout)
        layout.addWidget(font_preview_group)

        # 重置按钮
        reset_layout = QHBoxLayout()
        reset_layout.addStretch()
        self.reset_font_btn = QPushButton("\u91cd\u7f6e\u4e3a\u9ed8\u8ba4\u5b57\u4f53")
        _standard_settings_button(self.reset_font_btn, 132)
        self.reset_font_btn.setAccessibleName('重置为默认字体')
        self.reset_font_btn.clicked.connect(self.reset_font_settings)
        reset_layout.addWidget(self.reset_font_btn)
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
        self._apply_current_theme(selected_theme_css)

    def update_theme_preview(self):
        if not hasattr(self, 'preview_note'):
            return
        selected_theme_name = self.theme_combo.currentText()
        selected_theme_css = self.themes.get(selected_theme_name, "soft_yellow.css")
        css_path = os.path.join(get_styles_dir(), selected_theme_css)
        if os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8') as f:
                css_content = f.read()
            canvas = _colour_from_value(
                _css_value(css_content, 'StickyNote', 'background-color', '#FFFFCC'), '#FFFFCC'
            ).name()
            text = _colour_from_value(
                _css_value(css_content, 'StickyNote', 'color', '#000000'), '#000000'
            ).name()
            field = _colour_from_value(
                _css_value(css_content, 'QLineEdit', 'background-color', canvas), canvas
            ).name()
            border = _colour_from_value(
                _css_value(css_content, 'QLineEdit', 'border', '#FFD700'), '#FFD700'
            ).name()
            button = _colour_from_value(
                _css_value(css_content, 'QPushButton', 'background-color', border), border
            ).name()
            button_text = _colour_from_value(
                _css_value(css_content, 'QPushButton', 'color', text), text
            ).name()
            self.preview_note.setStyleSheet(f'''
                QFrame#themePreview {{
                    background: {canvas}; border: 1px solid {border}; border-radius: 13px;
                }}
                QLineEdit#themePreviewTitle, QTextEdit#themePreviewContent {{
                    background: {field}; color: {text}; border: 1px solid {border};
                    border-radius: 7px; padding: 7px;
                }}
                QLineEdit#themePreviewTitle {{ font-weight: bold; min-height: 36px; }}
                QLabel[previewChip="true"] {{
                    background: {button}; color: {button_text}; border: 1px solid {border};
                    border-radius: 6px; padding: 2px 8px;
                }}
            ''')

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
        layout.setContentsMargins(*_SETTINGS_PAGE_MARGINS)
        layout.setSpacing(_SETTINGS_GROUP_SPACING)

        # 自动检查更新
        auto_group = QGroupBox("\u81ea\u52a8\u66f4\u65b0")
        auto_layout = QVBoxLayout()

        self.auto_update_checkbox = QCheckBox("\u542f\u52a8\u540e\u81ea\u52a8\u68c0\u67e5\u65b0\u7248\u672c")
        auto_check = self.manager.settings.get('auto_check_update', True)
        self.auto_update_checkbox.setChecked(auto_check)
        self.auto_update_checkbox.stateChanged.connect(self.on_auto_update_changed)
        auto_layout.addWidget(self.auto_update_checkbox)

        hint_label = QLabel("\u542f\u7528\u540e\uff0c\u6bcf\u6b21\u542f\u52a8\u5e94\u7528\u65f6\u4f1a\u5728\u540e\u53f0\u81ea\u52a8\u68c0\u67e5 GitHub \u662f\u5426\u6709\u65b0\u7248\u672c\u53d1\u5e03\u3002")
        hint_label.setProperty('settingsRole', 'muted')
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
        self.cancel_check_btn.setProperty('settingsRole', 'danger')
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
        self.update_status_label.setObjectName('updateStatus')
        self.update_status_label.setProperty('settingsRole', 'muted')
        self.update_status_label.setAccessibleName('更新检查状态')
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
        self._set_update_status_state('working')
        self.manager.check_for_updates(manual=True, source='settings')

    def on_cancel_check_update(self):
        """取消检查更新"""
        self.update_status_label.setText("\u6b63\u5728\u53d6\u6d88...")
        self._set_update_status_state('working')
        self.cancel_check_btn.setEnabled(False)
        self.manager.cancel_update_check()

    def _set_update_status_state(self, state: str):
        """Refresh the visual state without replacing the theme stylesheet."""
        self.update_status_label.setProperty('status', state)
        style = self.update_status_label.style()
        style.unpolish(self.update_status_label)
        style.polish(self.update_status_label)

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
            f'<h3>发现新版本 v{update_info["version"]}</h3>'
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

        self.later_update_btn = QPushButton("\u7a0d\u540e\u63d0\u9192")
        self.later_update_btn.setAccessibleName('稍后提醒更新')
        self.later_update_btn.clicked.connect(self._on_inline_later)
        btn_row.addWidget(self.later_update_btn)

        self.skip_update_btn = QPushButton("\u8df3\u8fc7\u6b64\u7248\u672c")
        self.skip_update_btn.setAccessibleName('跳过此版本')
        self.skip_update_btn.clicked.connect(self._on_inline_skip)
        btn_row.addWidget(self.skip_update_btn)

        btn_row.addStretch()

        self.install_update_btn = QPushButton("\u7acb\u5373\u66f4\u65b0")
        self.install_update_btn.setProperty('settingsRole', 'primary')
        self.install_update_btn.setAccessibleName('立即更新应用')
        self.install_update_btn.clicked.connect(self._on_inline_update)
        btn_row.addWidget(self.install_update_btn)

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
        self._set_update_status_state('idle')

    def _on_inline_skip(self):
        """行内'跳过此版本'按钮"""
        if hasattr(self, '_inline_update_info'):
            self.manager.settings['skip_version'] = self._inline_update_info['tag']
            self.manager.save_settings()
        self.inline_update_group.setVisible(False)
        self.update_status_label.setText("已跳过此版本")
        self._set_update_status_state('idle')

    def _on_inline_update(self):
        """行内'立即更新'按钮"""
        if hasattr(self, '_inline_update_info'):
            self.manager._start_download_update(self._inline_update_info)

    # ==================== 安全设置 ====================

    def setup_security_tab(self, tab_widget):
        layout = QVBoxLayout()
        layout.setContentsMargins(*_SETTINGS_PAGE_MARGINS)
        layout.setSpacing(_SETTINGS_GROUP_SPACING)

        # 主密码设置
        master_group = QGroupBox("主密码")
        master_layout = QVBoxLayout()

        hint = QLabel("设置主密码后，每次启动应用时需要输入密码。")
        hint.setWordWrap(True)
        hint.setProperty('settingsRole', 'muted')
        master_layout.addWidget(hint)

        self.master_pwd_checkbox = QCheckBox("启用主密码")
        has_master = bool(self.manager.config.get('security.require_master_password', False))
        self.master_pwd_checkbox.setChecked(has_master)
        self.master_pwd_checkbox.stateChanged.connect(self._on_master_pwd_toggled)
        master_layout.addWidget(self.master_pwd_checkbox)

        btn_row = QHBoxLayout()
        self.set_master_pwd_btn = QPushButton("设置/修改主密码")
        _standard_settings_button(self.set_master_pwd_btn, 144)
        self.set_master_pwd_btn.clicked.connect(self._on_set_master_password)
        btn_row.addWidget(self.set_master_pwd_btn)
        btn_row.addStretch()
        master_layout.addLayout(btn_row)

        master_group.setLayout(master_layout)
        layout.addWidget(master_group)

        # 加密说明
        info_label = QLabel("安全说明：便签加密使用 AES-256-GCM，密钥通过 PBKDF2 派生（480000 轮）。\n"
                           "密码哈希使用 Argon2id（回退到 PBKDF2）。")
        info_label.setWordWrap(True)
        info_label.setProperty('settingsRole', 'muted')
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
        layout.setContentsMargins(*_SETTINGS_PAGE_MARGINS)
        layout.setSpacing(_SETTINGS_GROUP_SPACING)

        # 启用同步
        self.sync_enabled_cb = QCheckBox("启用云同步")
        self.sync_enabled_cb.setChecked(self.manager.config.get('sync.enabled', False))
        self.sync_enabled_cb.stateChanged.connect(self._on_sync_enabled_changed)
        layout.addWidget(self.sync_enabled_cb)

        # 同步提供商
        provider_group = QGroupBox("同步提供商")
        provider_layout = QFormLayout()
        provider_layout.setHorizontalSpacing(14)
        provider_layout.setVerticalSpacing(_SETTINGS_FORM_SPACING)

        self.sync_provider_combo = QComboBox()
        _standard_settings_field(self.sync_provider_combo, 220)
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
        webdav_layout = QVBoxLayout()
        webdav_layout.setContentsMargins(14, 18, 14, 14)
        webdav_layout.setSpacing(_SETTINGS_FORM_SPACING)

        def add_webdav_field(label_text, field):
            """Use stacked label/field rows so long URLs never squeeze a row."""
            label = QLabel(label_text)
            label.setProperty('settingsRole', 'fieldLabel')
            label.setMinimumHeight(20)
            row = QVBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            row.addWidget(label)
            row.addWidget(field)
            webdav_layout.addLayout(row)

        self.webdav_url = QLineEdit()
        self.webdav_url.setObjectName('webdav_url')
        _standard_settings_field(self.webdav_url, 200)
        self.webdav_url.setText(self.manager.config.get('sync.webdav.url', ''))
        self.webdav_url.setPlaceholderText('https://dav.jianguoyun.com/dav/')
        add_webdav_field("服务器 URL:", self.webdav_url)

        self.webdav_user = QLineEdit()
        self.webdav_user.setObjectName('webdav_user')
        _standard_settings_field(self.webdav_user, 200)
        self.webdav_user.setText(self.manager.config.get('sync.webdav.username', ''))
        add_webdav_field("用户名:", self.webdav_user)

        self.webdav_pwd = QLineEdit()
        self.webdav_pwd.setObjectName('webdav_pwd')
        _standard_settings_field(self.webdav_pwd, 200)
        self.webdav_pwd.setEchoMode(QLineEdit.Password)
        protected_password = (
            self.manager.config.get('sync.webdav.password_encrypted', '')
            or self.manager.config.get('sync.webdav.password', '')
        )
        if protected_password:
            try:
                from features.secret_storage import reveal_secret
                self.webdav_pwd.setText(reveal_secret(protected_password))
            except Exception:
                self.webdav_pwd.clear()
                self.webdav_pwd.setPlaceholderText('凭据不可读取，请重新输入')
        add_webdav_field("密码:", self.webdav_pwd)

        self.webdav_path = QLineEdit()
        self.webdav_path.setObjectName('webdav_path')
        _standard_settings_field(self.webdav_path, 200)
        self.webdav_path.setText(self.manager.config.get('sync.webdav.remote_path', '/stickynote/'))
        add_webdav_field("远程路径:", self.webdav_path)

        self.save_webdav_btn = QPushButton("保存 WebDAV 配置")
        _standard_settings_button(self.save_webdav_btn, 132)
        self.save_webdav_btn.setProperty('settingsRole', 'primary')
        self.save_webdav_btn.clicked.connect(self._on_save_webdav)
        save_row = QHBoxLayout()
        save_row.setContentsMargins(0, 4, 0, 0)
        save_row.addStretch()
        save_row.addWidget(self.save_webdav_btn)
        webdav_layout.addLayout(save_row)

        webdav_group.setLayout(webdav_layout)
        layout.addWidget(webdav_group)

        # 自动同步
        auto_sync_layout = QVBoxLayout()
        auto_sync_layout.setSpacing(_SETTINGS_FORM_SPACING)
        self.auto_sync_cb = QCheckBox("自动同步")
        self.auto_sync_cb.setChecked(self.manager.config.get('sync.auto_sync', False))
        self.auto_sync_cb.stateChanged.connect(self._on_auto_sync_changed)
        auto_sync_layout.addWidget(self.auto_sync_cb)

        interval_row = QHBoxLayout()
        interval_row.setSpacing(8)
        interval_label = QLabel("同步间隔:")
        interval_label.setProperty('settingsRole', 'fieldLabel')
        interval_row.addWidget(interval_label)
        self.sync_interval_spin = QSpinBox()
        _standard_settings_field(self.sync_interval_spin, 130)
        self.sync_interval_spin.setRange(5, 1440)
        self.sync_interval_spin.setValue(self.manager.config.get('sync.sync_interval_minutes', 30))
        self.sync_interval_spin.setSuffix(" 分钟")
        self.sync_interval_spin.valueChanged.connect(self._on_sync_interval_changed)
        interval_row.addWidget(self.sync_interval_spin)
        interval_row.addStretch()
        auto_sync_layout.addLayout(interval_row)
        layout.addLayout(auto_sync_layout)

        layout.addStretch()
        tab_widget.setLayout(layout)

    def _on_sync_enabled_changed(self):
        self.manager.config.set('sync.enabled', self.sync_enabled_cb.isChecked())
        self._refresh_sync_engine()

    def _on_sync_provider_changed(self, idx):
        provider = 'local' if idx == 1 else 'webdav'
        self.manager.config.set('sync.provider', provider)
        self._refresh_sync_engine()

    def _refresh_sync_engine(self):
        """Apply persisted sync settings immediately when the manager supports it."""
        setup_sync_engine = getattr(self.manager, 'setup_sync_engine', None)
        if callable(setup_sync_engine):
            setup_sync_engine()

    def _on_save_webdav(self):
        from features.secret_storage import protect_secret
        try:
            protected_password = protect_secret(self.webdav_pwd.text())
        except Exception as exc:
            QMessageBox.warning(self, '保存失败', f'无法安全保存 WebDAV 密码：{exc}')
            return
        self.manager.config.set('sync.webdav.url', self.webdav_url.text())
        self.manager.config.set('sync.webdav.username', self.webdav_user.text())
        self.manager.config.set('sync.webdav.password_encrypted', protected_password)
        self.manager.config.set('sync.webdav.password', '')
        self.manager.config.set('sync.webdav.remote_path', self.webdav_path.text())
        self._refresh_sync_engine()
        QMessageBox.information(self, '保存成功', 'WebDAV 配置已保存。')

    def _on_auto_sync_changed(self):
        self.manager.config.set('sync.auto_sync', self.auto_sync_cb.isChecked())
        self._refresh_sync_engine()

    def _on_sync_interval_changed(self, val):
        self.manager.config.set('sync.sync_interval_minutes', val)
        self._refresh_sync_engine()

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
        layout.setContentsMargins(*_SETTINGS_PAGE_MARGINS)
        layout.setSpacing(_SETTINGS_GROUP_SPACING)

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
            no_plugin.setProperty('settingsRole', 'muted')
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
                    desc_label.setProperty('settingsRole', 'muted')
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
                desc_label.setProperty('settingsRole', 'muted')
                plugin_layout.addWidget(desc_label)

                form_layout = QFormLayout()
                form_layout.setHorizontalSpacing(14)
                form_layout.setVerticalSpacing(_SETTINGS_FORM_SPACING)

                field_widgets = {}

                for field in fields:
                    key = field['key']
                    label = field.get('label', key)
                    ftype = field.get('type', 'text')
                    default = field.get('default', '')
                    current_value = plugin.config.get(key, default)

                    if ftype == 'bool':
                        w = QCheckBox()
                        w.setMinimumHeight(_SETTINGS_FIELD_HEIGHT)
                        w.setChecked(bool(current_value))
                        form_layout.addRow(label, w)

                    elif ftype == 'select':
                        w = QComboBox()
                        _standard_settings_field(w)
                        options = field.get('options', [])
                        w.addItems([str(o) for o in options])
                        idx = w.findText(str(current_value))
                        if idx >= 0:
                            w.setCurrentIndex(idx)
                        form_layout.addRow(label, w)

                    elif ftype == 'int':
                        w = QSpinBox()
                        _standard_settings_field(w)
                        w.setRange(field.get('min', 0), field.get('max', 9999))
                        w.setValue(int(current_value) if current_value else default)
                        suffix = field.get('suffix', '')
                        if suffix:
                            w.setSuffix(f' {suffix}')
                        form_layout.addRow(label, w)

                    else:  # 'text' or default
                        w = QLineEdit()
                        _standard_settings_field(w)
                        w.setText(str(current_value))
                        w.setPlaceholderText(str(default))
                        form_layout.addRow(label, w)

                    safe_plugin_name = re.sub(r'[^0-9A-Za-z_]+', '_', plugin_name).strip('_')
                    safe_field_key = re.sub(r'[^0-9A-Za-z_]+', '_', str(key)).strip('_')
                    w.setObjectName(
                        f'plugin_{safe_plugin_name or "item"}_{safe_field_key or "field"}'
                    )
                    w.setAccessibleName(f'{plugin_name} {label}')

                    # 帮助提示
                    help_text = field.get('help', '')
                    if help_text:
                        help_label = QLabel(f'  {help_text}')
                        help_label.setProperty('settingsRole', 'muted')
                        form_layout.addRow('', help_label)

                    field_widgets[key] = (ftype, w)

                plugin_layout.addLayout(form_layout)

                # 保存按钮
                save_btn = QPushButton('保存配置')
                save_btn.setFixedWidth(100)
                save_btn.setAccessibleName(f'保存 {plugin_name} 配置')
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
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.shortcuts_scroll = QScrollArea()
        self.shortcuts_scroll.setObjectName('shortcutSettingsScroll')
        self.shortcuts_scroll.setWidgetResizable(True)
        self.shortcuts_scroll.setFrameShape(QFrame.NoFrame)
        self.shortcuts_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName('shortcutSettingsContent')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(*_SETTINGS_PAGE_MARGINS)
        layout.setSpacing(_SETTINGS_GROUP_SPACING)

        hint = QLabel('自定义全局快捷键。点击“录制”后按下新的快捷键组合。')
        hint.setWordWrap(True)
        hint.setProperty('settingsRole', 'muted')
        layout.addWidget(hint)

        # 快捷键列表
        shortcuts_group = QGroupBox('全局快捷键')
        shortcuts_layout = QFormLayout()
        shortcuts_layout.setSpacing(10)

        # Keep the UI and runtime on the same action/default contract.
        shortcut_definitions = get_shortcut_definitions()
        self._shortcut_definitions = shortcut_definitions

        self._shortcut_editors = {}

        for action_name, spec in shortcut_definitions.items():
            label_text = spec['label']
            default_combo = spec['default']
            # 从配置读取当前值
            current = self.manager.config.get(f'shortcuts.{action_name}', default_combo)

            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)

            combo_label = QLabel(current)
            combo_label.setFixedWidth(160)
            combo_label.setMinimumHeight(32)
            combo_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            combo_label.setProperty('shortcutBadge', True)
            combo_label.setAccessibleName(f'{label_text}当前快捷键')

            record_btn = QPushButton('录制')
            _standard_settings_button(record_btn, 76)
            record_btn.setAccessibleName(f'录制{label_text}快捷键')

            reset_btn = QPushButton('重置')
            _standard_settings_button(reset_btn, 68)
            reset_btn.setAccessibleName(f'重置{label_text}快捷键')

            # 录制按钮逻辑
            def _start_record(lbl, btn, action, default):
                btn.setText('按下...')
                btn.setEnabled(False)
                self._recording_shortcut = True
                self._record_target = (lbl, btn, action, default)
                # 安装事件过滤器
                self.installEventFilter(self._ShortcutRecorder(self, lbl, btn, action))

            def _reset_shortcut(lbl, btn, action, default, action_label=label_text):
                lbl.setText(default)
                self._set_shortcut_status(
                    f'{action_label}已恢复为 {default}，点击“保存快捷键”后立即应用。',
                    'info',
                )

            record_btn.clicked.connect(
                lambda checked, l=combo_label, b=record_btn, a=action_name, d=default_combo:
                _start_record(l, b, a, d)
            )
            reset_btn.clicked.connect(
                lambda checked, l=combo_label, b=record_btn, a=action_name,
                d=default_combo, reset=_reset_shortcut: reset(l, b, a, d)
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

        status_row = QHBoxLayout()
        self.shortcut_status_icon = QLabel()
        self.shortcut_status_icon.setFixedSize(20, 20)
        self.shortcut_status_icon.setAccessibleName('快捷键状态图标')
        self.shortcut_status_label = QLabel('快捷键配置待检查')
        self.shortcut_status_label.setWordWrap(True)
        self.shortcut_status_label.setProperty('settingsRole', 'muted')
        self.shortcut_status_label.setAccessibleName('快捷键状态')
        status_row.addWidget(self.shortcut_status_icon)
        status_row.addWidget(self.shortcut_status_label, 1)
        layout.addLayout(status_row)
        self._set_shortcut_status(
            '快捷键配置会在保存时校验，并立即尝试重新注册。',
            'info',
        )

        # 提示
        note = QLabel('提示：快捷键组合必须包含 Ctrl、Shift 或 Alt 修饰键。\n'
                     '保存后会立即重新注册；若系统占用或组合冲突，会在此处显示原因。')
        note.setProperty('settingsRole', 'muted')
        note.setWordWrap(True)
        layout.addWidget(note)

        # 保存按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.apply_recommended_btn = QPushButton('应用推荐组合')
        _standard_settings_button(self.apply_recommended_btn, 132)
        self.apply_recommended_btn.setAccessibleName('应用推荐快捷键组合')
        self.apply_recommended_btn.setToolTip('仅替换四个便签动作的快捷键，不修改其他设置')
        self.apply_recommended_btn.clicked.connect(self.apply_recommended_shortcuts)
        btn_layout.addWidget(self.apply_recommended_btn)
        self.save_shortcuts_btn = QPushButton('保存快捷键')
        _standard_settings_button(self.save_shortcuts_btn, 112)
        self.save_shortcuts_btn.setProperty('settingsRole', 'primary')
        self.save_shortcuts_btn.setAccessibleName('保存快捷键配置')
        self.save_shortcuts_btn.clicked.connect(self._save_shortcuts)
        btn_layout.addWidget(self.save_shortcuts_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()
        self.shortcuts_scroll.setWidget(content)
        outer_layout.addWidget(self.shortcuts_scroll)
        tab_widget.setLayout(outer_layout)

    def _set_shortcut_status(self, message, kind='info'):
        """Render shortcut diagnostics with both an icon and explicit text."""
        label = getattr(self, 'shortcut_status_label', None)
        icon_label = getattr(self, 'shortcut_status_icon', None)
        if label is None:
            return
        icons = {
            'info': QStyle.SP_MessageBoxInformation,
            'success': QStyle.SP_DialogApplyButton,
            'warning': QStyle.SP_MessageBoxWarning,
            'error': QStyle.SP_MessageBoxCritical,
        }
        icon = QApplication.style().standardIcon(icons.get(kind, QStyle.SP_MessageBoxInformation))
        if icon_label is not None:
            icon_label.setPixmap(icon.pixmap(18, 18))
            icon_label.setToolTip(message)
        label.setText(str(message))
        label.setProperty('shortcutStatusKind', kind)
        label.style().unpolish(label)
        label.style().polish(label)

    def _shortcut_values_from_ui(self):
        return {
            action_name: label.text().strip()
            for action_name, (label, _) in self._shortcut_editors.items()
        }

    def _shortcut_error_text(self, error):
        action = error.get('action', '')
        spec = getattr(self, '_shortcut_definitions', {}).get(action, {})
        label = spec.get('label', action)
        combination = error.get('combination', '')
        reason = error.get('reason', 'invalid')
        conflict_action = error.get('conflict_with', '')
        conflict_spec = getattr(self, '_shortcut_definitions', {}).get(
            conflict_action, {}
        )
        conflict_label = conflict_spec.get('label', conflict_action)
        reason_text = {
            'invalid': '不是有效的单键修饰组合',
            'duplicate': f'与“{conflict_label}”重复',
            'system_conflict': '系统中已被其他程序占用',
            'registration_failed': '系统注册失败',
            'registration_error': '系统注册异常',
            'windows_unavailable': '当前系统不支持全局注册',
            'runtime_error': '运行时异常',
        }.get(reason, reason)
        return f'{label}：{combination or "（空）"}，{reason_text}'

    def _save_shortcuts(self, values=None, source='manual', *_args):
        if not isinstance(values, dict):
            values = self._shortcut_values_from_ui()
        validation = validate_shortcut_map(values)
        if not validation['ok']:
            text = '\n'.join(self._shortcut_error_text(error) for error in validation['errors'])
            self._set_shortcut_status(f'快捷键冲突或无效：\n{text}', 'error')
            return False

        apply_method = getattr(self.manager, 'apply_shortcut_settings', None)
        if callable(apply_method):
            report = apply_method(validation['normalized'])
        else:
            # Compatibility path for lightweight managers used by plugins/tests.
            for action_name, combination in validation['normalized'].items():
                try:
                    self.manager.config.set(
                        f'shortcuts.{action_name}', combination, auto_save=False,
                    )
                except TypeError:
                    self.manager.config.set(f'shortcuts.{action_name}', combination)
            save = getattr(self.manager.config, 'save', None)
            if callable(save):
                save()
            replace = getattr(getattr(self.manager, 'shortcut_manager', None),
                              'replace_global_shortcuts', None)
            report = replace(validation['normalized']) if callable(replace) else {
                'ok': True,
                'registered': dict(validation['normalized']),
                'errors': [],
            }

        if not report.get('ok', False):
            text = '\n'.join(self._shortcut_error_text(error) for error in report.get('errors', []))
            self._set_shortcut_status(f'快捷键未应用：\n{text or "未知注册错误"}', 'error')
            return False

        for action_name, combination in validation['normalized'].items():
            label, _ = self._shortcut_editors.get(action_name, (None, None))
            if label is not None:
                label.setText(combination)
        self._set_shortcut_status(
            '快捷键已保存并立即生效。' if source == 'manual'
            else '推荐快捷键已应用并立即生效。',
            'success',
        )
        QMessageBox.information(
            self,
            '已保存',
            '快捷键配置已保存并立即生效。',
        )
        return True

    def apply_recommended_shortcuts(self, *_args):
        recommended = {
            action_name: spec['default']
            for action_name, spec in self._shortcut_definitions.items()
        }
        for action_name, combination in recommended.items():
            label, _ = self._shortcut_editors.get(action_name, (None, None))
            if label is not None:
                label.setText(combination)
        return self._save_shortcuts(recommended, source='recommended')

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

                canonical = canonical_shortcut(combo)
                if not canonical:
                    self._finish_recording('快捷键无效：必须包含修饰键和一个主键。', 'error')
                    return True

                # 冲突检测
                conflict = self._check_conflict(canonical)
                if conflict:
                    self._finish_recording(
                        f'快捷键冲突：{canonical} 已被“{conflict}”使用，请选择其他组合。',
                        'error',
                    )
                    return True

                self.label.setText(canonical)
                self._finish_recording('快捷键已录制，点击“保存快捷键”后立即应用。', 'info')
                return True
            return False

        def _finish_recording(self, message, kind='info'):
            self.button.setText('录制')
            self.button.setEnabled(True)
            self.parent_dialog.removeEventFilter(self)
            self.parent_dialog._recording_shortcut = False
            self.parent_dialog._set_shortcut_status(message, kind)

        def _check_conflict(self, combo: str) -> Optional[str]:
            """检查快捷键是否与其他动作冲突"""
            if not hasattr(self.parent_dialog, '_shortcut_editors'):
                return None
            for action_name, (label, _) in self.parent_dialog._shortcut_editors.items():
                if action_name != self.action_name and canonical_shortcut(label.text()) == combo:
                    spec = getattr(self.parent_dialog, '_shortcut_definitions', {}).get(action_name, {})
                    return spec.get('label', action_name)
            return None


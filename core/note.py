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
import sys
import time
import copy
import ctypes
import shutil
import tempfile

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QMessageBox, QCheckBox,
    QColorDialog, QSystemTrayIcon, QMenu, QAction,
    QStackedWidget, QTextBrowser, QTextEdit, QInputDialog, QFileDialog,
    QListWidget, QDialog, QLineEdit, QFrame, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, QPoint, QRect, QRectF, QPointF, QMimeData, QTimer, QThread, QSize, QPropertyAnimation, QEasingCurve, QEvent, pyqtSignal
from PyQt5.QtGui import (
    QFont, QColor, QPalette, QCursor, QPainter, QPen, QTextCharFormat,
    QIcon, QPixmap, QPainterPath, QBrush, QImage, QRegion
)

from features.undo_redo import UndoRedoLineEdit, UndoRedoTextEdit, UndoRedoManager
from features.positioning import get_position_manager
from features.formatter import ContentFormatter
from features.tag import TagChipWidget
from features.richtext import RichTextActions
from core import get_styles_dir, __version__
from core.ui_preferences import (
    DEFAULT_SETTINGS_TOOL_ORDER, SETTINGS_TOOL_ORDER_KEY,
    normalize_settings_tool_order,
)

# 窗口调整大小检测边界宽度
RESIZE_MARGIN = 10

# 窗口吸附阈值 (像素)
SNAP_THRESHOLD = 15

# 保存防抖延迟 (毫秒)
SAVE_DEBOUNCE_MS = 500

# Compact desktop toolbar metrics.  Keep a little extra vertical breathing
# room for the horizontal scrollbar: on Windows the style can reserve more
# than the nominal 7 px even when the QSS handle is slim.
TOOL_BUTTON_HEIGHT = 32
TOOL_PAGE_HEIGHT = 60
TOOL_PANEL_HEIGHT = 68
TOOL_CONTENT_MIN_HEIGHT = 44


def _shape_refresh_event_types():
    """Return Qt screen/DPR event enums available in this PyQt build.

    PyQt5 distributions differ: some expose ``ScreenChangeInternal`` and/or
    ``DevicePixelRatioChange`` while older builds omit one of them.  Looking
    them up dynamically keeps every ordinary ``changeEvent`` safe.
    """
    event_types = []
    for event_name in ('ScreenChangeInternal', 'DevicePixelRatioChange'):
        event_type = getattr(QEvent, event_name, None)
        if event_type is not None:
            event_types.append(event_type)
    return tuple(event_types)


def _semantic_ui_tokens(is_dark: bool, high_contrast: bool = False) -> dict:
    """Return the note window's semantic visual tokens.

    Theme files still own the user's note palette.  These tokens only style
    the editor chrome, so controls remain legible and consistent when a
    custom theme is selected.  Keeping the semantic layer in Python also
    avoids scattering per-state colors through QSS strings.
    """
    if high_contrast:
        return {
            'canvas': '#000000', 'surface': '#111111', 'surface_alt': '#1A1A1A',
            'text': '#FFFFFF', 'muted': '#FFFFFF', 'border': '#FFFF00',
            'focus': '#FFFFFF', 'accent': '#FFFF00', 'accent_text': '#000000',
            'danger': '#FF6B6B', 'danger_border': '#FF6B6B',
            'selection': '#FFFF00', 'selection_text': '#000000',
            'radius_control': 5, 'radius_field': 6, 'radius_panel': 6,
        }
    if is_dark:
        return {
            'canvas': '#171A1F', 'surface': '#222831', 'surface_alt': '#2B323D',
            'text': '#F3F4F6', 'muted': '#AAB4C2', 'border': '#465160',
            'focus': '#8AB4F8', 'accent': '#8AB4F8', 'accent_text': '#172033',
            'danger': '#FCA5A5', 'danger_border': '#B85C62',
            'selection': '#315A8A', 'selection_text': '#FFFFFF',
            'radius_control': 6, 'radius_field': 8, 'radius_panel': 8,
        }
    return {
        'canvas': '#F7F8FA', 'surface': '#FFFFFF', 'surface_alt': '#F0F2F5',
        'text': '#1F2937', 'muted': '#64748B', 'border': '#D7DCE3',
        'focus': '#2F6FED', 'accent': '#2F6FED', 'accent_text': '#FFFFFF',
        'danger': '#B42318', 'danger_border': '#E2A5A0',
        'selection': '#CFE0FF', 'selection_text': '#102A56',
        'radius_control': 6, 'radius_field': 8, 'radius_panel': 8,
    }


def _rgba_for_hex(value: str, alpha: float) -> str:
    """Convert a CSS hex color to a Qt-friendly rgba() value."""
    color = QColor(value)
    if not color.isValid():
        color = QColor('#FFFFFF' if alpha >= 0.5 else '#000000')
    alpha_value = round(max(0.0, min(1.0, alpha)) * 255)
    return f'rgba({color.red()}, {color.green()}, {color.blue()}, {alpha_value})'


def _css_property_color(css: str, selector: str, properties=('background-color', 'background', 'color', 'border')):
    """Read the first simple hex/rgb color for a selector from a theme CSS."""
    match = re.search(rf'{re.escape(selector)}\s*\{{([^}}]*)\}}', css, re.I | re.S)
    if not match:
        return None
    block = match.group(1)
    for prop in properties:
        # `color` must not match the suffix of `background-color`.
        prop_match = re.search(
            rf'(?<![-\w]){re.escape(prop)}\s*:\s*([^;]+)', block, re.I
        )
        if prop_match:
            value = prop_match.group(1).strip()
            color = QColor(value)
            if color.isValid():
                return color.name()
            hex_match = re.search(r'#[0-9a-fA-F]{3,8}', value)
            if hex_match:
                return hex_match.group(0)
    return None


def _normalise_color(value, fallback=''):
    """Return a stable #rrggbb color or the supplied fallback."""
    color = QColor(str(value or '').strip())
    return color.name() if color.isValid() else fallback


def _relative_luminance(value) -> float:
    color = QColor(value)
    if not color.isValid():
        return 0.0

    def channel(component):
        component /= 255.0
        return component / 12.92 if component <= 0.04045 else ((component + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(color.red()) + 0.7152 * channel(color.green()) + 0.0722 * channel(color.blue())


def _contrast_ratio(foreground, background) -> float:
    lighter = max(_relative_luminance(foreground), _relative_luminance(background))
    darker = min(_relative_luminance(foreground), _relative_luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def _mix_colors(first, second, amount: float) -> str:
    first_color = QColor(first)
    second_color = QColor(second)
    if not first_color.isValid():
        first_color = QColor('#000000')
    if not second_color.isValid():
        second_color = QColor('#FFFFFF')
    amount = max(0.0, min(1.0, amount))
    return QColor(
        round(first_color.red() * (1.0 - amount) + second_color.red() * amount),
        round(first_color.green() * (1.0 - amount) + second_color.green() * amount),
        round(first_color.blue() * (1.0 - amount) + second_color.blue() * amount),
    ).name()


def _readable_color(preferred, background, minimum=4.5) -> str:
    """Keep a valid preferred color when readable, otherwise pick black/white."""
    preferred = _normalise_color(preferred)
    background = _normalise_color(background, '#FFFFFF')
    if preferred and _contrast_ratio(preferred, background) >= minimum:
        return preferred
    # Exact black/white guarantee the widest possible fallback contrast.  A
    # near-black fallback can miss 4.5:1 on mid-tone theme surfaces.
    candidates = ('#000000', '#FFFFFF')
    return max(candidates, key=lambda candidate: _contrast_ratio(candidate, background))


def _contrasting_surface(preferred, background, minimum=3.0) -> str:
    """Move a themed surface toward black/white until its boundary is visible."""
    preferred = _normalise_color(preferred, '#808080')
    background = _normalise_color(background, '#FFFFFF')
    if _contrast_ratio(preferred, background) >= minimum:
        return preferred
    target = max(('#111111', '#FFFFFF'), key=lambda candidate: _contrast_ratio(candidate, background))
    for step in range(1, 11):
        candidate = _mix_colors(preferred, target, step / 10.0)
        if _contrast_ratio(candidate, background) >= minimum:
            return candidate
    return target


def _has_supported_image_signature(path: str) -> bool:
    """Reject obviously corrupt files before passing them to Qt image plugins."""
    try:
        with open(path, 'rb') as image_file:
            header = image_file.read(16)
    except OSError:
        return False
    return (
        header.startswith(b'\x89PNG\r\n\x1a\n') or
        header.startswith(b'\xff\xd8\xff') or
        header.startswith((b'GIF87a', b'GIF89a')) or
        header.startswith(b'BM') or
        (header.startswith(b'RIFF') and header[8:12] == b'WEBP')
    )


def _make_vector_icon(kind: str, color: str = '#334155', size: int = 20, monochrome: bool = False) -> QIcon:
    """Create a small, platform-independent action icon.

    The app used emoji glyphs for several actions.  Those glyphs vary wildly
    between Windows font packs (and can render as empty squares), so the
    primary action vocabulary is drawn with Qt primitives instead.  The
    function deliberately has no dependency on an icon font or image file,
    keeping frozen/portable builds self-contained.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.45, size / 11.0))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    margin = size * 0.18
    inner = size - margin * 2

    def draw_glyph(text, rect=None, pixel_size=None, bold=False, italic=False):
        """Draw a conventional formatting glyph with the Windows UI font."""
        glyph_font = QFont('Segoe UI')
        glyph_font.setPixelSize(pixel_size or max(11, round(size * .66)))
        glyph_font.setBold(bold)
        glyph_font.setItalic(italic)
        painter.save()
        painter.setFont(glyph_font)
        painter.setPen(QPen(QColor(color)))
        painter.drawText(rect or QRectF(0, 0, size, size), Qt.AlignCenter, text)
        painter.restore()

    def draw_letter_a(left=.24, right=.76, top=.20, bottom=.76):
        middle = (left + right) / 2
        painter.drawLine(int(size * left), int(size * bottom),
                         int(size * middle), int(size * top))
        painter.drawLine(int(size * middle), int(size * top),
                         int(size * right), int(size * bottom))
        painter.drawLine(int(size * (left + .10)), int(size * .57),
                         int(size * (right - .10)), int(size * .57))

    if kind in ('undo', 'redo'):
        mirror = kind == 'redo'
        painter.drawArc(int(margin + 1), int(margin + 1), int(inner - 2),
                        int(inner - 2), 45 * 16 if not mirror else  -225 * 16,
                        255 * 16)
        if mirror:
            painter.drawLine(int(size - margin - 1), int(margin + 3),
                             int(size - margin - 1), int(margin + 8))
            painter.drawLine(int(size - margin - 1), int(margin + 3),
                             int(size - margin - 6), int(margin + 3))
        else:
            painter.drawLine(int(margin + 1), int(margin + 3),
                             int(margin + 1), int(margin + 8))
            painter.drawLine(int(margin + 1), int(margin + 3),
                             int(margin + 7), int(margin + 3))
    elif kind == 'tag':
        path = QPainterPath()
        path.moveTo(size * .18, size * .38)
        path.lineTo(size * .58, size * .18)
        path.lineTo(size * .84, size * .44)
        path.lineTo(size * .44, size * .82)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawEllipse(QPointF(size * .56, size * .36), size * .045, size * .045)
    elif kind == 'bell':
        painter.drawArc(int(size * .27), int(size * .20), int(size * .46),
                        int(size * .52), 25 * 16, 130 * 16)
        painter.drawLine(int(size * .27), int(size * .64), int(size * .73), int(size * .64))
        painter.drawLine(int(size * .35), int(size * .64), int(size * .31), int(size * .73))
        painter.drawLine(int(size * .65), int(size * .64), int(size * .69), int(size * .73))
        painter.drawArc(int(size * .43), int(size * .70), int(size * .14), int(size * .12), 180 * 16, 180 * 16)
    elif kind in ('lock', 'unlock'):
        painter.drawRoundedRect(QRectF(size * .25, size * .45, size * .50, size * .36), size * .06, size * .06)
        if kind == 'lock':
            painter.drawArc(int(size * .34), int(size * .20), int(size * .32), int(size * .42), 0, 180 * 16)
        else:
            painter.drawArc(int(size * .36), int(size * .20), int(size * .32), int(size * .42), 25 * 16, 125 * 16)
        painter.drawLine(int(size * .50), int(size * .56), int(size * .50), int(size * .68))
    elif kind == 'link':
        painter.drawRoundedRect(QRectF(size * .08, size * .34, size * .47, size * .28), size * .13, size * .13)
        painter.drawRoundedRect(QRectF(size * .45, size * .38, size * .47, size * .28), size * .13, size * .13)
        painter.drawLine(int(size * .40), int(size * .48), int(size * .60), int(size * .48))
    elif kind == 'image':
        painter.drawRoundedRect(QRectF(size * .14, size * .18, size * .72, size * .64), size * .05, size * .05)
        painter.drawEllipse(QPointF(size * .68, size * .34), size * .06, size * .06)
        path = QPainterPath()
        path.moveTo(size * .20, size * .73)
        path.lineTo(size * .42, size * .50)
        path.lineTo(size * .57, size * .64)
        path.lineTo(size * .69, size * .52)
        path.lineTo(size * .84, size * .73)
        painter.drawPath(path)
    elif kind == 'backlink':
        painter.drawLine(int(size * .23), int(size * .50), int(size * .80), int(size * .50))
        painter.drawLine(int(size * .23), int(size * .50), int(size * .42), int(size * .31))
        painter.drawLine(int(size * .23), int(size * .50), int(size * .42), int(size * .69))
        painter.drawArc(int(size * .39), int(size * .22), int(size * .40), int(size * .56), -80 * 16, 160 * 16)
    elif kind in ('font_decrease', 'font_increase'):
        draw_letter_a(.10, .60, .20, .78)
        painter.drawLine(int(size * .62), int(size * .50), int(size * .88), int(size * .50))
        if kind == 'font_increase':
            painter.drawLine(int(size * .75), int(size * .37), int(size * .75), int(size * .63))
    elif kind in ('bold', 'italic'):
        if kind == 'bold':
            path = QPainterPath()
            path.moveTo(size * .28, size * .18)
            path.lineTo(size * .28, size * .82)
            path.moveTo(size * .28, size * .18)
            path.lineTo(size * .50, size * .18)
            path.cubicTo(size * .78, size * .18, size * .78, size * .49,
                         size * .50, size * .49)
            path.lineTo(size * .28, size * .49)
            path.moveTo(size * .50, size * .49)
            path.cubicTo(size * .80, size * .49, size * .80, size * .82,
                         size * .50, size * .82)
            path.lineTo(size * .28, size * .82)
            painter.drawPath(path)
        else:
            painter.drawLine(int(size * .44), int(size * .20), int(size * .72), int(size * .20))
            painter.drawLine(int(size * .28), int(size * .80), int(size * .56), int(size * .80))
            painter.drawLine(int(size * .62), int(size * .20), int(size * .38), int(size * .80))
    elif kind in ('font_color', 'underline', 'strike'):
        if kind == 'font_color':
            draw_letter_a(.25, .75, .16, .68)
        elif kind == 'underline':
            underline_path = QPainterPath()
            underline_path.moveTo(size * .28, size * .20)
            underline_path.lineTo(size * .28, size * .50)
            underline_path.cubicTo(size * .28, size * .70, size * .72, size * .70,
                                   size * .72, size * .50)
            underline_path.lineTo(size * .72, size * .20)
            painter.drawPath(underline_path)
            painter.drawLine(int(size * .22), int(size * .78), int(size * .78), int(size * .78))
        else:
            strike_path = QPainterPath()
            strike_path.moveTo(size * .70, size * .24)
            strike_path.cubicTo(size * .55, size * .13, size * .28, size * .18,
                                size * .30, size * .36)
            strike_path.cubicTo(size * .32, size * .50, size * .68, size * .45,
                                size * .70, size * .63)
            strike_path.cubicTo(size * .72, size * .80, size * .43, size * .87,
                                size * .27, size * .74)
            painter.drawPath(strike_path)
            painter.drawLine(int(size * .20), int(size * .52), int(size * .80), int(size * .52))
        if kind == 'font_color':
            accent = color if monochrome else '#EF4444'
            painter.setPen(QPen(QColor(accent), max(2.0, size / 7.0), Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(int(size * .24), int(size * .78), int(size * .76), int(size * .78))
    elif kind in ('superscript', 'subscript'):
        painter.drawLine(int(size * .16), int(size * .34), int(size * .50), int(size * .72))
        painter.drawLine(int(size * .50), int(size * .34), int(size * .16), int(size * .72))
        top = .08 if kind == 'superscript' else .57
        two_path = QPainterPath()
        two_path.moveTo(size * .59, size * (top + .10))
        two_path.cubicTo(size * .67, size * top, size * .84, size * top,
                         size * .84, size * (top + .10))
        two_path.lineTo(size * .60, size * (top + .28))
        two_path.lineTo(size * .85, size * (top + .28))
        painter.drawPath(two_path)
    elif kind in ('align_left', 'align_center', 'align_right'):
        lengths = (0.62, 0.82, 0.54)
        for index, fraction in enumerate(lengths):
            y = size * (0.28 + index * .22)
            width = size * fraction
            if kind == 'align_left':
                x = size * .18
            elif kind == 'align_right':
                x = size * (.82 - fraction)
            else:
                x = size * (.50 - fraction / 2)
            painter.drawLine(int(x), int(y), int(x + width), int(y))
    elif kind in ('ordered_list', 'unordered_list'):
        for index in range(3):
            y = size * (0.28 + index * .22)
            if kind == 'unordered_list':
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(color))
                painter.drawEllipse(QPointF(size * .25, y), size * .045, size * .045)
            else:
                draw_glyph(
                    str(index + 1),
                    QRectF(size * .10, y - size * .11, size * .25, size * .22),
                    max(7, round(size * .30)), bold=True,
                )
            painter.setPen(pen)
            painter.drawLine(int(size * .42), int(y), int(size * .82), int(y))
    elif kind == 'highlight':
        painter.drawLine(int(size * .27), int(size * .73), int(size * .74), int(size * .26))
        painter.drawLine(int(size * .20), int(size * .80), int(size * .46), int(size * .74))
        painter.drawLine(int(size * .54), int(size * .25), int(size * .75), int(size * .46))
        accent = color if monochrome else '#FBBF24'
        painter.setPen(QPen(QColor(accent), max(2.0, size / 7.0), Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(int(size * .29), int(size * .69), int(size * .63), int(size * .35))
    elif kind == 'clear':
        painter.drawLine(int(size * .28), int(size * .28), int(size * .72), int(size * .72))
        painter.drawLine(int(size * .72), int(size * .28), int(size * .28), int(size * .72))
    elif kind == 'trash':
        painter.drawRoundedRect(QRectF(size * .25, size * .28, size * .50, size * .57), size * .04, size * .04)
        painter.drawLine(int(size * .20), int(size * .24), int(size * .80), int(size * .24))
        painter.drawLine(int(size * .40), int(size * .17), int(size * .60), int(size * .17))
        painter.drawLine(int(size * .42), int(size * .40), int(size * .42), int(size * .72))
        painter.drawLine(int(size * .58), int(size * .40), int(size * .58), int(size * .72))
    elif kind == 'hide':
        painter.drawEllipse(QRectF(size * .17, size * .31, size * .66, size * .38))
        painter.drawEllipse(QPointF(size * .50, size * .50), size * .08, size * .08)
        painter.drawLine(int(size * .20), int(size * .20), int(size * .80), int(size * .80))
    elif kind == 'help':
        painter.drawEllipse(QRectF(size * .18, size * .18, size * .64, size * .64))
        painter.drawArc(int(size * .38), int(size * .30), int(size * .24), int(size * .22), 25 * 16, 220 * 16)
        painter.drawLine(int(size * .50), int(size * .52), int(size * .50), int(size * .61))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QPointF(size * .50, size * .70), size * .045, size * .045)
    elif kind == 'markdown':
        # Hash + two text lines is a compact Markdown cue without relying on
        # a platform font containing a special glyph.
        painter.drawLine(int(size * .22), int(size * .32), int(size * .42), int(size * .32))
        painter.drawLine(int(size * .22), int(size * .46), int(size * .42), int(size * .46))
        painter.drawLine(int(size * .27), int(size * .23), int(size * .27), int(size * .55))
        painter.drawLine(int(size * .37), int(size * .23), int(size * .37), int(size * .55))
        painter.drawLine(int(size * .54), int(size * .30), int(size * .78), int(size * .30))
        painter.drawLine(int(size * .54), int(size * .47), int(size * .78), int(size * .47))
        painter.drawLine(int(size * .54), int(size * .64), int(size * .70), int(size * .64))
    elif kind == 'tool_format':
        painter.drawLine(int(size * .22), int(size * .72), int(size * .50), int(size * .28))
        painter.drawLine(int(size * .50), int(size * .28), int(size * .76), int(size * .72))
        painter.drawLine(int(size * .34), int(size * .54), int(size * .64), int(size * .54))
    elif kind == 'tool_settings':
        for y, knob_x in ((.30, .62), (.50, .38), (.70, .57)):
            painter.drawLine(int(size * .20), int(size * y), int(size * .80), int(size * y))
            painter.setBrush(QColor(color))
            painter.drawEllipse(QPointF(size * knob_x, size * y), size * .055, size * .055)
            painter.setBrush(Qt.NoBrush)
    elif kind == 'tool_actions':
        # A four-cell toolbox grid communicates "all note actions" more
        # clearly than the legacy ellipsis/menu glyph.
        for x in (.24, .54):
            for y in (.24, .54):
                painter.drawRoundedRect(
                    QRectF(size * x, size * y, size * .22, size * .22),
                    size * .035, size * .035,
                )
    elif kind in ('edge_left', 'edge_right', 'edge_up', 'edge_down'):
        points = {
            'edge_left': ((.64, .25), (.36, .50), (.64, .75)),
            'edge_right': ((.36, .25), (.64, .50), (.36, .75)),
            'edge_up': ((.25, .64), (.50, .36), (.75, .64)),
            'edge_down': ((.25, .36), (.50, .64), (.75, .36)),
        }[kind]
        first, middle, last = points
        painter.drawLine(
            int(size * first[0]), int(size * first[1]),
            int(size * middle[0]), int(size * middle[1]),
        )
        painter.drawLine(
            int(size * middle[0]), int(size * middle[1]),
            int(size * last[0]), int(size * last[1]),
        )
        if kind in ('edge_left', 'edge_right'):
            rail_x = .80 if kind == 'edge_left' else .20
            painter.drawLine(
                int(size * rail_x), int(size * .27),
                int(size * rail_x), int(size * .73),
            )
        else:
            rail_y = .80 if kind == 'edge_up' else .20
            painter.drawLine(
                int(size * .27), int(size * rail_y),
                int(size * .73), int(size * rail_y),
            )
    elif kind == 'background':
        painter.drawRect(QRectF(size * .16, size * .22, size * .68, size * .56))
        painter.drawEllipse(QPointF(size * .67, size * .38), size * .07, size * .07)
        path = QPainterPath()
        path.moveTo(size * .21, size * .70)
        path.lineTo(size * .42, size * .48)
        path.lineTo(size * .56, size * .62)
        path.lineTo(size * .70, size * .50)
        path.lineTo(size * .80, size * .70)
        painter.drawPath(path)
    elif kind == 'clear_background':
        painter.drawRect(QRectF(size * .18, size * .22, size * .64, size * .56))
        painter.drawLine(int(size * .22), int(size * .24), int(size * .78), int(size * .76))
    painter.end()
    return QIcon(pixmap)


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

    # Keep the visual radius in one place.  The same logical radius is used
    # by the antialiased painter and the native hit-test mask below.
    WINDOW_CORNER_RADIUS = 14
    WINDOW_BORDER_WIDTH = 2

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
        self.background_image = self.note_data.get('background_image', '') or ''
        raw_font_color = self.note_data.get('font_color')
        normalised_font_color = _normalise_color(raw_font_color)
        self.font_color = normalised_font_color or '#000000'
        stored_font_mode = str(self.note_data.get('font_color_mode', '')).lower()
        if stored_font_mode == 'manual' and not normalised_font_color:
            # Corrupt/manual data must not force an unreadable black fallback
            # on a dark theme. Keep the note usable and return to theme mode.
            stored_font_mode = 'theme'
        if stored_font_mode not in {'theme', 'manual'}:
            # Legacy notes always stored black, even when the user never chose
            # it. Preserve non-black choices; migrate the legacy default to
            # theme-driven text.
            stored_font_mode = 'manual' if self.font_color != '#000000' else 'theme'
        self.font_color_mode = stored_font_mode
        self.background_text_color = _normalise_color(
            self.note_data.get('background_text_color')
        )
        self.background_control_color = _normalise_color(
            self.note_data.get('background_control_color')
        )
        try:
            stored_control_opacity = float(self.note_data.get('control_opacity', 1.0))
        except (TypeError, ValueError):
            stored_control_opacity = 1.0
        self.control_opacity = max(0.2, min(1.0, stored_control_opacity))
        self._background_pixmap = QPixmap()
        self._background_source = ''
        self._background_invalid = False

        # A frameless top-level QWidget is rectangular until an explicit
        # native mask is applied. Keep shape state separate from the paint
        # cache so it can be rebuilt after resize/DPI changes.
        self._window_shape_ready = False
        self._window_shape_dpr = 1.0

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
        self._border_pen.setWidth(self.WINDOW_BORDER_WIDTH)

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
        # The native top-level window remains rectangular unless Qt is
        # allowed to composite transparent pixels.  The rounded painter and
        # QRegion mask below provide the visible and hit-test boundaries.
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAutoFillBackground(False)
        self.setMinimumSize(240, 240)
        self._load_background_pixmap()

        # 启用鼠标追踪，以便悬停在边缘时自动切换为缩放光标
        self.setMouseTracking(True)

        # 主布局
        main_layout = QVBoxLayout()
        # Keep a little breathing room around each control while preserving the
        # existing frameless-window resize hit area.
        main_layout.setContentsMargins(RESIZE_MARGIN + 2, RESIZE_MARGIN + 2,
                                       RESIZE_MARGIN + 2, RESIZE_MARGIN + 2)
        main_layout.setSpacing(8)

        # 标题编辑
        self.title_edit = PlainLineEdit()
        self.title_edit.setObjectName('noteTitle')
        self.title_edit.setMinimumHeight(42)
        self.title_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.title_edit.setPlaceholderText('便签标题')
        self.title_edit.setAccessibleName('便签标题')
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
        self.editor_stack.setObjectName('editorStack')
        self.editor_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.editor_stack.setAccessibleName('便签编辑区')
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
        font_layout.setContentsMargins(4, 3, 4, 3)
        font_layout.setSpacing(8)

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

        # Recompose the same controls into bounded semantic groups. Keeping
        # the existing button instances preserves every signal and state.
        while font_layout.count():
            font_layout.takeAt(0)
        for separator in (
                self.separator1, self.separator2, self.separator3,
                self.separator4, self.separator5, self.separator6,
                self.separator7):
            separator.setParent(self)
            separator.hide()
        format_group_specs = (
            ('formatTypeScaleGroup', '字体大小',
             (self.decrease_font_btn, self.increase_font_btn)),
            ('formatEmphasisGroup', '字体强调',
             (self.bold_btn, self.italic_btn)),
            ('formatColorGroup', '字体颜色', (self.color_btn,)),
            ('formatDecorationGroup', '下划线和删除线',
             (self.underline_btn, self.strikethrough_btn)),
            ('formatScriptGroup', '上标和下标',
             (self.superscript_btn, self.subscript_btn)),
            ('formatAlignmentGroup', '文本对齐',
             (self.align_left_btn, self.align_center_btn, self.align_right_btn)),
            ('formatListGroup', '列表',
             (self.ordered_list_btn, self.unordered_list_btn)),
            ('formatHighlightGroup', '高亮',
             (self.highlight_btn, self.clear_highlight_btn)),
        )
        self.format_tool_groups = []
        for object_name, accessible_name, controls in format_group_specs:
            for control in controls:
                control.setFixedSize(34, TOOL_BUTTON_HEIGHT)
            group = self._make_tool_group(object_name, accessible_name, controls)
            self.format_tool_groups.append(group)
            font_layout.addWidget(group)

        # The formatting strip contains more actions than a compact note can
        # display at once.  A horizontal scroller keeps every action available
        # on narrow windows instead of letting buttons overlap or disappear.
        format_panel = QWidget()
        format_panel.setObjectName('formatPanel')
        format_panel.setAttribute(Qt.WA_StyledBackground, True)
        format_panel.setLayout(font_layout)
        format_panel.setMinimumHeight(TOOL_CONTENT_MIN_HEIGHT)
        format_panel.adjustSize()
        self.format_panel = format_panel
        self.format_scroll = QScrollArea()
        self.format_scroll.setObjectName('formatScroll')
        self.format_scroll.setWidget(format_panel)
        self.format_scroll.setWidgetResizable(False)
        self.format_scroll.setFrameShape(QFrame.NoFrame)
        self.format_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.format_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.format_scroll.setFixedHeight(TOOL_PAGE_HEIGHT)
        self.format_scroll.setMinimumWidth(0)
        self.format_scroll.setMinimumSize(0, TOOL_PAGE_HEIGHT)
        self.format_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # 选项轨道。它与格式、操作轨道共享一行空间，避免窄窗口中
        # 固定宽度的透明度滑块挤掉功能按钮。
        settings_layout = QHBoxLayout()
        settings_layout.setContentsMargins(4, 3, 4, 3)
        settings_layout.setSpacing(8)

        self.transparency_slider = QSlider(Qt.Horizontal)
        self.transparency_slider.setRange(20, 100)
        self.transparency_slider.setValue(int(self.note_data.get('opacity', 0.9) * 100))
        self.transparency_slider.setSingleStep(1)
        self.transparency_slider.setFixedWidth(112)
        self.transparency_slider.valueChanged.connect(self.change_transparency)
        self.transparency_label = QLabel('\u900f\u660e\u5ea6:')
        settings_layout.addWidget(self.transparency_label)
        settings_layout.addWidget(self.transparency_slider)

        self.control_opacity_slider = QSlider(Qt.Horizontal)
        self.control_opacity_slider.setObjectName('controlOpacitySlider')
        self.control_opacity_slider.setRange(20, 100)
        self.control_opacity_slider.setValue(int(self.control_opacity * 100))
        self.control_opacity_slider.setSingleStep(1)
        self.control_opacity_slider.setFixedWidth(112)
        self.control_opacity_slider.setAccessibleName('控件透明度')
        self.control_opacity_slider.valueChanged.connect(self.change_control_opacity)
        self.control_opacity_label = QLabel(f'控件透明度: {int(self.control_opacity * 100)}%')
        settings_layout.addWidget(self.control_opacity_label)
        settings_layout.addWidget(self.control_opacity_slider)

        self.background_btn = QPushButton('背景图')
        self.background_btn.setObjectName('backgroundButton')
        self.background_btn.setToolTip('为当前便签选择背景图片')
        self.background_btn.setAccessibleName('选择便签背景图片')
        self.background_btn.setFixedSize(96, 30)
        self.background_btn.clicked.connect(self.choose_background_image)
        settings_layout.addWidget(self.background_btn)

        self.clear_background_btn = QPushButton('清除背景')
        self.clear_background_btn.setObjectName('clearBackgroundButton')
        self.clear_background_btn.setToolTip('清除当前便签背景图片，恢复主题颜色')
        self.clear_background_btn.setAccessibleName('清除便签背景图片')
        self.clear_background_btn.setFixedSize(108, 30)
        self.clear_background_btn.clicked.connect(self.clear_background_image)
        settings_layout.addWidget(self.clear_background_btn)

        self.background_text_color_btn = QPushButton('文字色')
        self.background_text_color_btn.setObjectName('backgroundTextColorButton')
        self.background_text_color_btn.setToolTip(
            '设置图片背景下的默认文字色；已手动着色文字不受影响'
        )
        self.background_text_color_btn.setFixedSize(90, 30)
        self.background_text_color_btn.clicked.connect(self.choose_background_text_color)
        settings_layout.addWidget(self.background_text_color_btn)

        self.background_control_color_btn = QPushButton('控件色')
        self.background_control_color_btn.setObjectName('backgroundControlColorButton')
        self.background_control_color_btn.setToolTip('设置图片背景下的按钮、图标和焦点色')
        self.background_control_color_btn.setFixedSize(90, 30)
        self.background_control_color_btn.clicked.connect(self.choose_background_control_color)
        settings_layout.addWidget(self.background_control_color_btn)

        self.reset_background_colors_btn = QPushButton('颜色自动')
        self.reset_background_colors_btn.setObjectName('resetBackgroundColorsButton')
        self.reset_background_colors_btn.setToolTip('恢复根据背景图和主题自动选择的高对比颜色')
        self.reset_background_colors_btn.setFixedSize(104, 30)
        self.reset_background_colors_btn.clicked.connect(self.reset_background_colors)
        settings_layout.addWidget(self.reset_background_colors_btn)

        self.topmost_checkbox = QCheckBox("\u603b\u5728\u6700\u524d")
        self.topmost_checkbox.setChecked(self.note_data.get('always_on_top', True))
        self.topmost_checkbox.stateChanged.connect(self.toggle_always_on_top)
        settings_layout.addWidget(self.topmost_checkbox)

        self.format_checkbox = QCheckBox("\u667a\u80fd\u683c\u5f0f\u5316")
        self.format_checkbox.setChecked(self.note_data.get('auto_format_enabled', True))
        self.format_checkbox.setToolTip('\u542f\u7528\u540e\u7c98\u8d34\u65f6\u81ea\u52a8\u683c\u5f0f\u5316')
        self.format_checkbox.stateChanged.connect(self.toggle_auto_format)
        settings_layout.addWidget(self.format_checkbox)

        # Background, opacity and behaviour are separate regions rather than
        # one uninterrupted row.  The controls and connections stay intact.
        while settings_layout.count():
            settings_layout.takeAt(0)
        for button in (
                self.background_btn, self.clear_background_btn,
                self.background_text_color_btn, self.background_control_color_btn,
                self.reset_background_colors_btn):
            button.setFixedHeight(TOOL_BUTTON_HEIGHT)
        settings_group_specs = (
            ('background', 'settingsBackgroundGroup', '背景图片',
             (self.background_btn, self.clear_background_btn)),
            ('background_colors', 'settingsColorGroup', '背景文字和控件颜色',
             (self.background_text_color_btn, self.background_control_color_btn,
              self.reset_background_colors_btn)),
            ('control_opacity', 'settingsControlOpacityGroup', '控件透明度',
             (self.control_opacity_label, self.control_opacity_slider)),
            ('window_opacity', 'settingsWindowOpacityGroup', '便签透明度',
             (self.transparency_label, self.transparency_slider)),
            ('behaviour', 'settingsBehaviourGroup', '便签行为',
             (self.topmost_checkbox, self.format_checkbox)),
        )
        self.settings_tool_groups = []
        self.settings_tool_group_map = {}
        self.settings_layout = settings_layout
        for key, object_name, accessible_name, controls in settings_group_specs:
            group = self._make_tool_group(object_name, accessible_name, controls)
            self.settings_tool_groups.append(group)
            self.settings_tool_group_map[key] = group
        self.apply_settings_tool_order(self._configured_settings_tool_order())

        settings_panel = QWidget()
        settings_panel.setObjectName('settingsPanel')
        settings_panel.setLayout(settings_layout)
        settings_panel.setMinimumHeight(TOOL_CONTENT_MIN_HEIGHT)
        settings_panel.setAttribute(Qt.WA_StyledBackground, True)
        settings_panel.adjustSize()
        self.settings_panel = settings_panel
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setObjectName('settingsScroll')
        self.settings_scroll.setWidget(settings_panel)
        self.settings_scroll.setWidgetResizable(False)
        self.settings_scroll.setFrameShape(QFrame.NoFrame)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.settings_scroll.setFixedHeight(TOOL_PAGE_HEIGHT)
        self.settings_scroll.setMinimumSize(0, TOOL_PAGE_HEIGHT)
        self.settings_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # 按钮布局
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(4, 3, 4, 3)
        buttons_layout.setSpacing(8)
        
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
        self.reminder_btn.setObjectName('reminderButton')
        self.reminder_btn.setToolTip('设置提醒')
        self.reminder_btn.setFixedSize(36, 30)
        self.reminder_btn.clicked.connect(self.open_reminder_dialog)
        buttons_layout.addWidget(self.reminder_btn)
        
        # 锁定/解锁按钮
        self.lock_btn = QPushButton('🔒' if self.is_locked else '🔓')
        self.lock_btn.setObjectName('lockButton')
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
        self.md_toggle_btn.setObjectName('markdownButton')
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
        self.delete_btn.setObjectName('deleteButton')
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

        while buttons_layout.count():
            buttons_layout.takeAt(0)
        for button in (
                self.undo_btn, self.redo_btn, self.tag_btn, self.reminder_btn,
                self.lock_btn, self.link_btn, self.image_btn, self.md_toggle_btn,
                self.backlink_btn, self.help_btn):
            button.setFixedSize(36, TOOL_BUTTON_HEIGHT)
        self.hide_btn.setFixedSize(76, TOOL_BUTTON_HEIGHT)
        self.delete_btn.setFixedSize(76, TOOL_BUTTON_HEIGHT)
        action_group_specs = (
            ('actionHistoryGroup', '撤销和重做',
             (self.undo_btn, self.redo_btn)),
            ('actionOrganiseGroup', '标签、提醒和锁定',
             (self.tag_btn, self.reminder_btn, self.lock_btn)),
            ('actionInsertGroup', '插入和关联内容',
             (self.link_btn, self.image_btn, self.md_toggle_btn, self.backlink_btn)),
            ('actionWindowGroup', '帮助和窗口显示',
             (self.help_btn, self.hide_btn)),
            ('actionDangerGroup', '删除便签', (self.delete_btn,)),
        )
        self.action_tool_groups = []
        for object_name, accessible_name, controls in action_group_specs:
            group = self._make_tool_group(object_name, accessible_name, controls)
            self.action_tool_groups.append(group)
            buttons_layout.addWidget(group)

        action_panel = QWidget()
        action_panel.setObjectName('actionPanel')
        action_panel.setLayout(buttons_layout)
        action_panel.setMinimumHeight(TOOL_CONTENT_MIN_HEIGHT)
        action_panel.setAttribute(Qt.WA_StyledBackground, True)
        action_panel.adjustSize()
        self.action_panel = action_panel
        self.action_scroll = QScrollArea()
        self.action_scroll.setObjectName('actionScroll')
        self.action_scroll.setWidget(action_panel)
        self.action_scroll.setWidgetResizable(False)
        self.action_scroll.setFrameShape(QFrame.NoFrame)
        self.action_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.action_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.action_scroll.setFixedHeight(TOOL_PAGE_HEIGHT)
        self.action_scroll.setMinimumWidth(0)
        self.action_scroll.setMinimumSize(0, TOOL_PAGE_HEIGHT)
        self.action_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Signature tool rail: one compact row, three clearly named views.
        # This changes presentation only; every original control object and
        # signal remains intact inside its corresponding scrollable page.
        self.control_panel = QFrame()
        self.control_panel.setObjectName('controlPanel')
        tool_rail_layout = QHBoxLayout()
        tool_rail_layout.setContentsMargins(4, 4, 4, 4)
        tool_rail_layout.setSpacing(8)
        self.tool_rail_buttons = []
        for icon_kind, description in (
                ('tool_format', '显示文字格式工具'),
                ('tool_settings', '显示便签选项'),
                ('tool_actions', '显示便签功能')):
            button = QPushButton('')
            button.setCheckable(True)
            button.setFixedSize(36, 36)
            button.setProperty('toolRailIcon', icon_kind)
            button.setToolTip(description)
            button.setAccessibleName(description)
            button.setProperty('toolRailTab', True)
            self.tool_rail_buttons.append(button)
        self.tool_rail_nav = self._make_tool_group(
            'toolRailNav', '底部工具页切换', self.tool_rail_buttons
        )
        self.tool_rail_nav.setProperty('toolNavigation', True)
        self.tool_rail_nav.setFixedHeight(42)
        tool_rail_layout.addWidget(self.tool_rail_nav)
        self.tool_rail_stack = QStackedWidget()
        self.tool_rail_stack.setObjectName('toolRailStack')
        # The pages are independently horizontally scrollable.  Ignoring the
        # stack's content size hint lets the nav rail keep its own fixed width
        # instead of forcing the page to compress into the nav buttons.
        self.tool_rail_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.tool_rail_stack.setMinimumWidth(0)
        self.tool_rail_stack.setFixedHeight(TOOL_PAGE_HEIGHT)
        self.tool_rail_stack.addWidget(self.format_scroll)
        self.tool_rail_stack.addWidget(self.settings_scroll)
        self.tool_rail_stack.addWidget(self.action_scroll)
        for index, button in enumerate(self.tool_rail_buttons):
            button.clicked.connect(lambda checked=False, page=index: self._show_tool_rail(page))
        tool_rail_layout.addWidget(self.tool_rail_stack, 1)
        self.control_panel.setLayout(tool_rail_layout)
        self.control_panel.setMinimumHeight(TOOL_PANEL_HEIGHT)
        self.control_panel.setAttribute(Qt.WA_StyledBackground, True)
        main_layout.addWidget(self.control_panel)
        self._show_tool_rail(2)

        # Install a deterministic vector icon vocabulary after all buttons have
        # been created.  Text labels remain in tooltips and accessible names,
        # while icons stay crisp on every Windows font configuration.
        self._prepare_action_icons()

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
        # Tab order must be configured after every nested page has a common
        # top-level window; doing it earlier triggers Qt warnings for controls
        # hosted by the stacked tool rail.
        self._configure_accessibility()

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

        self.color_btn.setChecked(self.font_color_mode == 'manual')
        self.color_btn.setToolTip(
            '手动字体颜色（优先于主题和背景图默认文字色）'
        )

        initial_color_icon = (
            self.font_color
            if self.font_color_mode == 'manual'
            else self._current_icon_color()
        )
        self.color_btn.setIcon(_make_vector_icon(
            'font_color', initial_color_icon,
            monochrome=self._has_background_image(),
        ))

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
            initial_size = self.recommended_initial_size()
            smart_position = position_manager.get_smart_position(
                self.note_id, initial_size
            )
            self.resize(initial_size)
            self.move(smart_position)
            position_manager.register_window_position(
                self.note_id, smart_position, initial_size
            )

        # Geometry is now final enough to build the initial native rounded
        # region. Subsequent interactive/DPI resizes rebuild it in
        # ``resizeEvent``.
        self._window_shape_ready = True
        self._update_window_shape()

        # Windows 11 Mica/backdrop is an optional enhancement.  The helper is
        # deliberately called after geometry is established (so a native HWND
        # exists) and never changes translucency flags on its own.  Unsupported
        # systems and offscreen test sessions use the normal opaque gradient.
        self._acrylic_enabled = self._try_enable_system_backdrop()
        self.setProperty('acrylicEnabled', self._acrylic_enabled)

        # 更新提醒按钮显示
        self.update_reminder_display()

        # 刷新标签芯片
        self.refresh_tag_chips()

    # ==================== 字体和样式 ====================

    def _configured_settings_tool_order(self):
        """Read the shared order without making manager-less notes fragile."""
        manager = getattr(self, 'manager', None)
        if manager is not None:
            getter = getattr(manager, 'get_settings_tool_order', None)
            if callable(getter):
                return normalize_settings_tool_order(getter())
            config = getattr(manager, 'config', None)
            if config is not None and hasattr(config, 'get'):
                return normalize_settings_tool_order(
                    config.get(SETTINGS_TOOL_ORDER_KEY, None)
                )
        return list(DEFAULT_SETTINGS_TOOL_ORDER)

    def apply_settings_tool_order(self, order):
        """Apply a validated left-to-right group order without recreating controls."""
        normalised = normalize_settings_tool_order(order)
        layout = getattr(self, 'settings_layout', None)
        group_map = getattr(self, 'settings_tool_group_map', {})
        if layout is None or not group_map:
            return normalised
        for group in group_map.values():
            layout.removeWidget(group)
        ordered_groups = []
        for key in normalised:
            group = group_map.get(key)
            if group is None:
                continue
            layout.addWidget(group)
            ordered_groups.append(group)
        self.settings_tool_groups = ordered_groups
        layout.invalidate()
        layout.activate()
        self._refresh_tool_group_widths()
        return normalised

    def _show_tool_rail(self, index: int):
        """Switch the visible tool rail without recreating any controls."""
        if not hasattr(self, 'tool_rail_stack'):
            return
        index = max(0, min(index, self.tool_rail_stack.count() - 1))
        self.tool_rail_stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.tool_rail_buttons):
            button.setChecked(button_index == index)
        current_page = self.tool_rail_stack.currentWidget()
        if current_page is not None:
            current_page.setFocusPolicy(Qt.NoFocus)

    def _make_tool_group(self, object_name: str, accessible_name: str, widgets):
        """Create one bounded toolbar group without recreating its controls."""
        group = QFrame()
        group.setObjectName(object_name)
        group.setProperty('toolGroup', True)
        group.setAccessibleName(accessible_name)
        group.setFocusPolicy(Qt.NoFocus)
        group.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        group_layout = QHBoxLayout(group)
        group_layout.setContentsMargins(3, 2, 3, 2)
        group_layout.setSpacing(3)
        for widget in widgets:
            if isinstance(widget, QPushButton):
                widget.setProperty('compactToolButton', True)
            group_layout.addWidget(widget)
        group.setFixedHeight(38)
        # Fixed-width groups prevent Qt from compressing adjacent fixed-size
        # buttons into each other when the outer scroll viewport is narrow.
        group.setFixedWidth(group_layout.sizeHint().width() + 2)
        return group

    def _refresh_tool_group_widths(self):
        """Re-fit groups after a label, icon, font or theme changes size."""
        collections = (
            getattr(self, 'format_tool_groups', []),
            getattr(self, 'settings_tool_groups', []),
            getattr(self, 'action_tool_groups', []),
            [getattr(self, 'tool_rail_nav', None)],
        )
        for groups in collections:
            for group in groups:
                if group is None or group.layout() is None:
                    continue
                group.layout().invalidate()
                group.layout().activate()
                group.setFixedWidth(max(
                    group.minimumSizeHint().width(),
                    group.layout().sizeHint().width() + 2,
                ))

        # QScrollArea(widgetResizable=False) owns the content widget's
        # geometry.  Resizing a child group alone leaves the panel at the
        # width it had during initUI, so newly-polished labels/sliders can be
        # painted into the next group. Recompute the real content width and
        # push it through the scroll area after every theme/icon refresh.
        for panel_name, scroll_name in (
                ('format_panel', 'format_scroll'),
                ('settings_panel', 'settings_scroll'),
                ('action_panel', 'action_scroll')):
            panel = getattr(self, panel_name, None)
            if panel is None or panel.layout() is None:
                continue
            panel_layout = panel.layout()
            panel_layout.invalidate()
            panel_layout.activate()
            hint = panel_layout.sizeHint()
            panel.resize(max(1, hint.width()), max(
                TOOL_CONTENT_MIN_HEIGHT, hint.height()
            ))
            panel.updateGeometry()
            scroll = getattr(self, scroll_name, None)
            if scroll is not None:
                scroll.updateGeometry()
                scroll.viewport().update()

        # Reflow the nav/stack split after the nav group's width changes.  The
        # stack is intentionally allowed to become narrow; each page then
        # exposes its full content through its own horizontal scrollbar.
        control_panel = getattr(self, 'control_panel', None)
        if control_panel is not None and control_panel.layout() is not None:
            control_layout = control_panel.layout()
            control_layout.invalidate()
            control_layout.activate()
            control_panel.updateGeometry()
        stack = getattr(self, 'tool_rail_stack', None)
        if stack is not None:
            stack.updateGeometry()

    def recommended_initial_size(self):
        """Size a new note so the complete action page is visible at first launch."""
        self._refresh_tool_group_widths()
        action_panel = getattr(self, 'action_panel', None)
        nav = getattr(self, 'tool_rail_nav', None)
        control_panel = getattr(self, 'control_panel', None)
        main_layout = self.layout()
        if (action_panel is None or action_panel.layout() is None or
                nav is None or control_panel is None or
                control_panel.layout() is None or main_layout is None):
            return QSize(640, 300)

        action_panel.layout().invalidate()
        action_panel.layout().activate()
        page_width = max(
            action_panel.width(), action_panel.layout().sizeHint().width()
        )
        rail_layout = control_panel.layout()
        rail_margins = rail_layout.contentsMargins()
        outer_margins = main_layout.contentsMargins()
        desired_width = (
            outer_margins.left() + outer_margins.right() +
            rail_margins.left() + rail_margins.right() +
            nav.width() + rail_layout.spacing() + page_width + 4
        )
        desired_width = max(self.minimumWidth(), desired_width)

        screen = QApplication.primaryScreen()
        if screen is not None:
            available_width = screen.availableGeometry().width()
            if available_width > 0:
                # Preserve a small grab margin while using the full desktop
                # width when that is what the complete action rail requires.
                desired_width = min(
                    desired_width,
                    max(self.minimumWidth(), available_width - 16),
                )
        return QSize(int(desired_width), max(self.minimumHeight(), 300))

    def _prepare_action_icons(self, color: str = '#334155', monochrome=None):
        """Apply the stable vector icon set to action buttons.

        Button object names and signals stay untouched.  Only presentation
        changes, and the original text remains available through tooltips and
        accessible names for keyboard/screen-reader users.
        """
        icon_map = {
            'undo_btn': ('undo', '撤销 (Ctrl+Z)'),
            'redo_btn': ('redo', '重做 (Ctrl+Y)'),
            'tag_btn': ('tag', '设置标签'),
            'reminder_btn': ('bell', '设置提醒'),
            'lock_btn': ('lock' if self.is_locked else 'unlock',
                         '解锁便签' if self.is_locked else '锁定便签'),
            'link_btn': ('link', '插入链接'),
            'image_btn': ('image', '插入图片'),
            'background_btn': ('background', '选择便签背景图片'),
            'clear_background_btn': ('clear_background', '清除便签背景图片'),
            'background_text_color_btn': ('font_color', '设置背景图默认文字色'),
            'background_control_color_btn': ('highlight', '设置背景图控件色'),
            'reset_background_colors_btn': ('clear', '背景图颜色恢复自动'),
            'md_toggle_btn': ('markdown', '切换 Markdown 预览'),
            'backlink_btn': ('backlink', '便签反向链接'),
            'delete_btn': ('trash', '删除便签'),
            'help_btn': ('help', '使用说明'),
            'hide_btn': ('hide', '隐藏便签'),
            'highlight_btn': ('highlight', '背景高亮'),
            'clear_highlight_btn': ('clear', '清除高亮'),
            'decrease_font_btn': ('font_decrease', '减小字号'),
            'increase_font_btn': ('font_increase', '增大字号'),
            'bold_btn': ('bold', '加粗'), 'italic_btn': ('italic', '斜体'),
            'color_btn': (
                'font_color', '手动字体颜色（优先于主题和背景图默认文字色）'
            ),
            'underline_btn': ('underline', '下划线'),
            'strikethrough_btn': ('strike', '删除线'),
            'superscript_btn': ('superscript', '上标'), 'subscript_btn': ('subscript', '下标'),
            'align_left_btn': ('align_left', '左对齐'), 'align_center_btn': ('align_center', '居中对齐'),
            'align_right_btn': ('align_right', '右对齐'), 'ordered_list_btn': ('ordered_list', '有序列表'),
            'unordered_list_btn': ('unordered_list', '无序列表'),
        }
        self._icon_color = color
        if monochrome is None:
            monochrome = self._has_background_image()
        for name, (kind, description) in icon_map.items():
            button = getattr(self, name, None)
            if button is None:
                continue
            icon_color = color
            if name == 'color_btn' and self.font_color_mode == 'manual' and not monochrome:
                icon_color = self.font_color
            button.setIcon(_make_vector_icon(kind, icon_color, monochrome=monochrome))
            button.setIconSize(QSize(19, 19))
            button.setAccessibleName(description)
            # Keep the compact action row icon-led.  Tooltips carry the full
            # label and remain visible for mouse and keyboard focus.
            if name not in (
                'delete_btn', 'hide_btn', 'background_btn', 'clear_background_btn',
                'background_text_color_btn', 'background_control_color_btn',
                'reset_background_colors_btn',
            ):
                button.setText('')
            button.setToolTip(description)
        if hasattr(self, 'clear_background_btn'):
            self.clear_background_btn.setEnabled(self._has_background_image())
        background_active = self._has_background_image()
        for name in ('background_text_color_btn', 'background_control_color_btn'):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(background_active)
        if hasattr(self, 'reset_background_colors_btn'):
            self.reset_background_colors_btn.setEnabled(
                background_active and bool(self.background_text_color or self.background_control_color)
            )
        self._refresh_tool_group_widths()

    def _configure_accessibility(self):
        """Keep existing actions named and keyboard-reachable."""
        for name, label in {
            'title_edit': '便签标题', 'text_edit': '便签内容编辑器',
            'transparency_slider': '便签透明度', 'topmost_checkbox': '总在最前',
            'format_checkbox': '智能格式化', 'delete_btn': '删除便签',
            'hide_btn': '隐藏便签',
            'control_opacity_slider': '控件透明度',
            'background_btn': '选择便签背景图片',
            'clear_background_btn': '清除便签背景图片',
            'background_text_color_btn': '设置背景图默认文字色',
            'background_control_color_btn': '设置背景图控件色',
            'reset_background_colors_btn': '背景图颜色恢复自动',
        }.items():
            control = getattr(self, name, None)
            if control is not None:
                control.setAccessibleName(label)
                control.setFocusPolicy(Qt.StrongFocus)
        action_names = [
            'decrease_font_btn', 'increase_font_btn', 'bold_btn', 'italic_btn',
            'color_btn', 'underline_btn', 'strikethrough_btn', 'superscript_btn',
            'subscript_btn', 'align_left_btn', 'align_center_btn', 'align_right_btn',
            'ordered_list_btn', 'unordered_list_btn', 'highlight_btn',
            'clear_highlight_btn', 'undo_btn', 'redo_btn', 'tag_btn',
            'reminder_btn', 'lock_btn', 'link_btn', 'image_btn', 'md_toggle_btn',
            'backlink_btn', 'delete_btn', 'help_btn', 'hide_btn',
        ]
        actions = []
        for name in action_names:
            control = getattr(self, name, None)
            if control is not None:
                control.setFocusPolicy(Qt.StrongFocus)
                actions.append(control)
        for name in ('format_scroll', 'settings_scroll', 'action_scroll'):
            control = getattr(self, name, None)
            if control is not None:
                control.setFocusPolicy(Qt.NoFocus)
        order = ([self.title_edit, self.text_edit] + self.tool_rail_buttons +
                 actions + [self.transparency_slider, self.control_opacity_slider,
                            self.background_btn, self.clear_background_btn,
                            self.background_text_color_btn,
                            self.background_control_color_btn,
                            self.reset_background_colors_btn,
                            self.topmost_checkbox, self.format_checkbox])
        for previous, current in zip(order, order[1:]):
            self.setTabOrder(previous, current)

    def _try_enable_system_backdrop(self) -> bool:
        """Best-effort Windows 11 acrylic backdrop with a safe no-op fallback.

        DWM is never required for rendering.  We avoid changing Qt's opacity
        or translucency attributes, so unsupported Windows versions, Linux,
        and offscreen test platforms keep the normal opaque themed surface.
        """
        if sys.platform != 'win32' or os.environ.get('QT_QPA_PLATFORM') in {'offscreen', 'minimal'}:
            return False
        try:
            version = sys.getwindowsversion()
            if (version.major, version.build) < (10, 22000):
                return False
            hwnd = int(self.winId()) if hasattr(self, 'winId') else 0
            if not hwnd:
                return False
            dwmapi = ctypes.windll.dwmapi
            # DWMWA_SYSTEMBACKDROP_TYPE = 38, value 3 = acrylic.
            backdrop_type = ctypes.c_int(3)
            result = dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), 38,
                ctypes.byref(backdrop_type), ctypes.sizeof(backdrop_type)
            )
            return result == 0
        except Exception:
            return False

    def _rounded_window_path(self, rect=None, inset=None):
        """Return the rounded path, inset so the border never paints square corners."""
        if rect is None:
            rect = QRectF(self.rect())
        elif not isinstance(rect, QRectF):
            rect = QRectF(rect)
        if inset is None:
            inset = self.WINDOW_BORDER_WIDTH / 2.0
        inset = max(0.0, float(inset))
        if inset:
            rect = rect.adjusted(inset, inset, -inset, -inset)
        if rect.width() <= 0 or rect.height() <= 0:
            return QPainterPath()
        radius = min(
            float(self.WINDOW_CORNER_RADIUS),
            rect.width() / 2.0,
            rect.height() / 2.0,
        )
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def _update_window_shape(self):
        """Rebuild the native rounded hit-test region after geometry changes.

        QRegion is deliberately derived from the same path used by
        ``paintEvent``.  The region is a binary hit-test boundary; antialiasing
        remains the painter's responsibility, so the visible edge stays
        smooth while the four corners are genuinely transparent/non-clickable.
        """
        if not getattr(self, '_window_shape_ready', False):
            return
        if self.width() <= 0 or self.height() <= 0:
            return
        try:
            # The hit-test mask follows the outer silhouette.  Painting uses
            # a one-pixel inset so the centred pen cannot protrude beyond it.
            path = self._rounded_window_path(inset=0)
            polygon = path.toFillPolygon().toPolygon()
            if polygon.isEmpty():
                self.clearMask()
                return
            self.setMask(QRegion(polygon))
            try:
                self._window_shape_dpr = float(self.devicePixelRatioF())
            except (AttributeError, TypeError, ValueError):
                self._window_shape_dpr = 1.0
        except Exception:
            # Some non-composited/offscreen Qt plugins do not implement
            # top-level masks.  Rendering still works; leave the best-effort
            # mask absent rather than making construction fail.
            logger.debug('无法更新便签圆角窗口区域', exc_info=True)

    def resizeEvent(self, event):
        """Keep the rounded region and Cover cache aligned with the window."""
        super().resizeEvent(event)
        if hasattr(self, '_background_scaled_size'):
            self._background_scaled_size = QSize()
        if hasattr(self, '_background_scaled_dpr'):
            self._background_scaled_dpr = 0.0
        if hasattr(self, '_background_scaled_cache'):
            self._background_scaled_cache = QPixmap()
        self._update_window_shape()
        if getattr(self, 'auto_hidden', False) and self.hide_tab is not None:
            self._position_hide_tab()

    def changeEvent(self, event):
        """Refresh shape/cache when Qt reports a screen or DPR transition."""
        super().changeEvent(event)
        if event.type() in _shape_refresh_event_types():
            if hasattr(self, '_background_scaled_size'):
                self._background_scaled_size = QSize()
            if hasattr(self, '_background_scaled_dpr'):
                self._background_scaled_dpr = 0.0
            if hasattr(self, '_background_scaled_cache'):
                self._background_scaled_cache = QPixmap()
            self._update_window_shape()

    def _background_candidates(self):
        """Return the stored background path and whether it is app-managed."""
        stored = str(getattr(self, 'background_image', '') or '').strip()
        if not stored:
            return '', False
        if os.path.isabs(stored):
            return os.path.realpath(stored), False
        candidate = os.path.realpath(os.path.join(self.notes_dir, stored))
        try:
            safe = os.path.normcase(os.path.commonpath([candidate, self.notes_dir])) == os.path.normcase(self.notes_dir)
        except ValueError:
            safe = False
        if not safe:
            return '', False
        images_prefix = os.path.normcase(os.path.join(self.notes_dir, 'images') + os.sep)
        return candidate, os.path.normcase(candidate).startswith(images_prefix)

    def _load_background_pixmap(self):
        """Load a custom background once; invalid/missing files fall back safely."""
        self._background_pixmap = QPixmap()
        self._background_source = ''
        self._background_scaled_cache = QPixmap()
        self._background_scaled_size = QSize()
        self._background_scaled_dpr = 1.0
        self._background_invalid = False
        path, _ = self._background_candidates()
        if not path or not os.path.isfile(path):
            self._background_invalid = bool(path)
            return False
        if not _has_supported_image_signature(path):
            self._background_invalid = True
            return False
        image = QImage(path)
        if image.isNull():
            self._background_invalid = True
            return False
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            self._background_invalid = True
            return False
        self._background_pixmap = pixmap
        self._background_source = path
        self._background_invalid = False
        return True

    def _managed_background_path(self, path):
        """Check whether path is this note's own managed image before deletion."""
        if not path:
            return False
        images_dir = os.path.realpath(os.path.join(self.notes_dir, 'images'))
        real_path = os.path.realpath(path)
        try:
            if os.path.normcase(os.path.commonpath([real_path, images_dir])) != os.path.normcase(images_dir):
                return False
        except ValueError:
            return False
        prefix = f'background_{self.note_id}_'
        return os.path.basename(real_path).startswith(prefix)

    def choose_background_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, '选择便签背景图片', '',
            '图片文件 (*.png *.jpg *.jpeg *.gif *.bmp *.webp)'
        )
        if not file_path:
            return False
        if not _has_supported_image_signature(file_path):
            QMessageBox.warning(self, '背景图片无效', '所选文件不是可识别的 PNG、JPG、GIF、BMP 或 WebP 图片。')
            return False
        image = QImage(file_path)
        if image.isNull():
            QMessageBox.warning(self, '背景图片无效', '无法读取所选图片，便签背景未改变。')
            return False
        images_dir = os.path.realpath(os.path.join(self.notes_dir, 'images'))
        os.makedirs(images_dir, exist_ok=True)
        base = os.path.basename(file_path)
        stem, ext = os.path.splitext(base)
        safe_stem = re.sub(r'[^0-9A-Za-z一-龥._-]+', '_', stem)[:60] or 'image'
        dest_name = f'background_{self.note_id}_{safe_stem}{ext.lower()}'
        dest = os.path.realpath(os.path.join(images_dir, dest_name))
        old_stored = self.background_image
        old_path, old_managed = self._background_candidates()
        had_background = self._has_background_image()
        stage_path = ''
        backup_path = ''
        destination_replaced = False
        try:
            if os.path.normcase(os.path.commonpath([dest, images_dir])) != os.path.normcase(images_dir):
                raise ValueError('背景图片路径不安全')
            if os.path.normcase(os.path.realpath(file_path)) != os.path.normcase(dest):
                stage_fd, stage_path = tempfile.mkstemp(
                    prefix=f'.background_{self.note_id}_stage_',
                    suffix=ext.lower(),
                    dir=images_dir,
                )
                os.close(stage_fd)
                shutil.copy2(file_path, stage_path)
                if QImage(stage_path).isNull():
                    raise ValueError('复制后的图片无法读取')
                if os.path.exists(dest):
                    backup_fd, backup_path = tempfile.mkstemp(
                        prefix=f'.background_{self.note_id}_backup_',
                        suffix=ext.lower(),
                        dir=images_dir,
                    )
                    os.close(backup_fd)
                    shutil.copy2(dest, backup_path)
                os.replace(stage_path, dest)
                stage_path = ''
                destination_replaced = True
            self.background_image = os.path.relpath(dest, self.notes_dir).replace(os.sep, '/')
            if not self._load_background_pixmap():
                raise ValueError('复制后的图片无法读取')
            if not had_background and self.control_opacity >= 0.999:
                self.control_opacity = 0.86
                self.control_opacity_slider.blockSignals(True)
                self.control_opacity_slider.setValue(86)
                self.control_opacity_slider.blockSignals(False)
                self.control_opacity_label.setText('控件透明度: 86%')
            self.apply_theme()
            # The icon helper derives monochrome mode from the successfully
            # loaded pixmap; keeping that decision in one place prevents a
            # stale/invalid image path from changing icon colors.
            self._prepare_action_icons(self._current_icon_color())
            if (old_managed and old_path and old_path != dest and
                    self._managed_background_path(old_path)):
                try:
                    os.remove(old_path)
                except OSError:
                    pass
            self.save_note()
            self.update()
            return True
        except Exception as exc:
            if destination_replaced:
                try:
                    if backup_path and os.path.exists(backup_path):
                        os.replace(backup_path, dest)
                        backup_path = ''
                    elif os.path.exists(dest):
                        os.remove(dest)
                except OSError:
                    logging.exception('恢复便签背景图片失败: %s', dest)
            self.background_image = old_stored
            self._load_background_pixmap()
            QMessageBox.warning(self, '背景图片失败', f'无法设置背景图片：{exc}')
            return False
        finally:
            for temporary_path in (stage_path, backup_path):
                if temporary_path and os.path.exists(temporary_path):
                    try:
                        os.remove(temporary_path)
                    except OSError:
                        pass

    def clear_background_image(self):
        old_path, old_managed = self._background_candidates()
        if old_managed and old_path and self._managed_background_path(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
        self.background_image = ''
        self._load_background_pixmap()
        self.apply_theme()
        self._prepare_action_icons(self._current_icon_color())
        self.save_note()
        self.update()
        return True

    def _current_icon_color(self):
        return getattr(self, '_icon_color', '#334155')

    def _has_background_image(self):
        return bool(getattr(self, '_background_pixmap', QPixmap()).isNull() is False)

    def _background_reference_color(self):
        """Return a small-sample average used only for automatic contrast."""
        if not self._has_background_image():
            return QColor('#FFFFFF')
        image = self._background_pixmap.toImage().scaled(
            16, 16, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        )
        red = green = blue = count = 0
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                if pixel.alpha() <= 8:
                    continue
                red += pixel.red()
                green += pixel.green()
                blue += pixel.blue()
                count += 1
        if not count:
            return QColor('#FFFFFF')
        return QColor(round(red / count), round(green / count), round(blue / count))

    def choose_background_text_color(self):
        if not self._has_background_image():
            return False
        styles = getattr(self, '_current_theme_styles', {})
        initial = self.background_text_color or styles.get('text', '#111111')
        color = QColorDialog.getColor(QColor(initial), self, '选择背景图默认文字色')
        if not color.isValid():
            return False
        # This is intentionally separate from font_color/font_color_mode.
        # Existing inline rich-text colors and a manual default font color win.
        self.background_text_color = color.name()
        self.apply_theme()
        self.save_note()
        return True

    def choose_background_control_color(self):
        if not self._has_background_image():
            return False
        styles = getattr(self, '_current_theme_styles', {})
        initial = self.background_control_color or styles.get('control_surface', '#666666')
        color = QColorDialog.getColor(QColor(initial), self, '选择背景图控件色')
        if not color.isValid():
            return False
        self.background_control_color = color.name()
        self.apply_theme()
        self.save_note()
        return True

    def reset_background_colors(self):
        self.background_text_color = ''
        self.background_control_color = ''
        self.apply_theme()
        if not self.is_deleted:
            self.save_note()
        return True

    def change_control_opacity(self, value):
        self.control_opacity = max(0.2, min(1.0, int(value) / 100.0))
        if hasattr(self, 'control_opacity_label'):
            self.control_opacity_label.setText(f'控件透明度: {int(self.control_opacity * 100)}%')
        if hasattr(self, 'theme'):
            self.apply_theme()
        if not self.is_deleted:
            self.save_note()

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
        font_style_sheet = f'''
            font-family: "{font_family}" !important;
            font-size: {font_size}pt !important;
            font-weight: {font_weight} !important;
            font-style: {font_style} !important;
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
        # A body selection is an inline formatting operation. Keep the
        # current default color as the dialog seed, but do not turn a
        # selection into a note-wide ``font_color_mode=manual`` override.
        body_cursor = self.text_edit.textCursor()
        has_body_selection = body_cursor.hasSelection()
        current_color = getattr(self, 'font_color', '#000000')
        if has_body_selection:
            selected_color = body_cursor.charFormat().foreground().color()
            if selected_color.isValid():
                current_color = selected_color.name()
        color = QColorDialog.getColor(QColor(current_color), self, '\u9009\u62e9\u5b57\u4f53\u989c\u8272')
        if not color.isValid():
            self.color_btn.setChecked(self.font_color_mode == 'manual')
            return False
        color_hex = color.name()
        if has_body_selection:
            # Apply only an inline foreground to the selected body range. In
            # particular, do not call apply_theme() here: changing the note's
            # default body color would recolor every unformatted character
            # and the title through the shared theme stylesheet.
            char_format = body_cursor.charFormat()
            char_format.setForeground(QColor(color_hex))
            body_cursor.mergeCharFormat(char_format)
            if not self.is_deleted:
                self.save_note()
            return True

        # With no selection, the color is the body editor's insertion/default
        # format. It may persist as the note's manual body color, but the
        # title color is resolved independently by _theme_tokens_from_css().
        char_format = self.text_edit.currentCharFormat()
        char_format.setForeground(QColor(color_hex))
        self.text_edit.setCurrentCharFormat(char_format)
        self.font_color = color_hex
        self.font_color_mode = 'manual'
        self.color_btn.setChecked(True)
        self.note_data['font_color'] = color_hex
        self.note_data['font_color_mode'] = 'manual'
        self.apply_theme()
        if not self.is_deleted:
            self.save_note()
        return True

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
        high_contrast = 'high_contrast' in str(getattr(self, 'theme', '')).lower()
        tokens = _semantic_ui_tokens(is_dark, high_contrast)
        # Compatibility aliases keep existing integrations source-compatible.
        return {
            **tokens,
            'separator_color': tokens['muted'], 'bg': tokens['surface_alt'],
            'color': tokens['text'], 'hover_bg': tokens['surface'],
            'pressed_bg': tokens['border'], 'checked_bg': tokens['accent'],
            'checked_color': tokens['accent_text'], 'focus_border': tokens['focus'],
            'muted': tokens['muted'], 'panel_bg': tokens['canvas'],
            'input_bg': tokens['surface'], 'input_border': tokens['border'],
            'editor_bg': tokens['surface'], 'card_start': tokens['surface'],
            'card_end': tokens['surface_alt'], 'accent_start': tokens['accent'],
            'accent_end': tokens['accent'], 'title_start': tokens['surface'],
            'title_end': tokens['surface'],
        }

    def _theme_tokens_from_css(self, css: str, is_dark: bool):
        """Overlay semantic chrome tokens with colors declared by the theme."""
        tokens = self.get_adaptive_control_styles(is_dark)
        selectors = {
            'canvas': ('StickyNote', ('background-color', 'background')),
            'surface': ('QTextEdit', ('background-color', 'background')),
            'text': ('QTextEdit', ('color',)),
            'border': ('QTextEdit', ('border',)),
            'accent': ('QPushButton', ('background-color', 'background')),
            'control_surface': ('QPushButton', ('background-color', 'background')),
            'control_text': ('QPushButton', ('color',)),
            'control_hover': ('QPushButton:hover', ('background-color', 'background')),
        }
        for key, (selector, properties) in selectors.items():
            color = _css_property_color(css, selector, properties)
            if color:
                tokens[key] = color
        tokens['surface_alt'] = tokens['surface']
        tokens['editor_bg'] = tokens['surface']
        tokens['input_bg'] = tokens['surface']
        tokens['title_surface'] = _css_property_color(
            css, 'QLineEdit', ('background-color', 'background')
        ) or tokens['surface']
        theme_title_text = _css_property_color(css, 'QLineEdit', ('color',)) or tokens['text']
        theme_title_border = _css_property_color(css, 'QLineEdit', ('border',)) or tokens['border']
        tokens.setdefault('control_surface', tokens['accent'])
        tokens.setdefault('control_text', tokens['text'])
        tokens.setdefault('control_hover', tokens['surface'])

        background_active = self._has_background_image()
        reference_surface = self._background_reference_color().name() if background_active else tokens['canvas']
        effective_editor_surface = (
            _mix_colors(reference_surface, tokens['editor_bg'], self.control_opacity)
            if background_active else tokens['editor_bg']
        )
        effective_title_surface = (
            _mix_colors(reference_surface, tokens['title_surface'], self.control_opacity)
            if background_active else tokens['title_surface']
        )

        theme_text = _readable_color(tokens['text'], tokens['editor_bg'], 4.5)
        theme_title_text = _readable_color(theme_title_text, tokens['title_surface'], 4.5)
        # The title has its own visual role. Resolve its theme/background
        # color before applying the body font override so a manual body color
        # can never leak into the title editor.
        effective_theme_title_text = _readable_color(
            theme_title_text, effective_title_surface, 4.5
        )
        if self.font_color_mode == 'manual':
            # Explicit manual font color is the body default only. Inline
            # rich-text colors remain even more specific inside the
            # QTextDocument, and the title keeps its own theme/background
            # color instead of inheriting the body setting.
            tokens['text'] = self.font_color
            tokens['title_text'] = effective_theme_title_text
        elif background_active and self.background_text_color:
            tokens['text'] = self.background_text_color
            tokens['title_text'] = self.background_text_color
        elif background_active:
            tokens['text'] = _readable_color(theme_text, effective_editor_surface, 4.5)
            tokens['title_text'] = effective_theme_title_text
        else:
            tokens['text'] = theme_text
            tokens['title_text'] = theme_title_text

        if background_active and self.background_control_color:
            tokens['control_surface'] = self.background_control_color
            tokens['accent'] = self.background_control_color
            target = '#111111' if QColor(reference_surface).lightness() > 128 else '#FFFFFF'
            tokens['control_hover'] = _mix_colors(self.background_control_color, target, 0.14)
        else:
            tokens['control_surface'] = _contrasting_surface(
                tokens['control_surface'], reference_surface, 3.0
            )
            tokens['accent'] = tokens['control_surface']
            tokens['control_hover'] = _contrasting_surface(
                tokens['control_hover'], reference_surface, 3.0
            )
        canvas_color = QColor(tokens['canvas'])
        text_color = QColor(tokens['text'])
        border_color = QColor(tokens['border'])
        high_contrast_theme = (
            'high_contrast' in str(getattr(self, 'theme', '')).lower() or
            (canvas_color.lightness() < 35 and text_color.lightness() > 220 and
             border_color.lightness() > 190)
        )
        if high_contrast_theme and not (background_active and self.background_control_color):
            # The theme's dark button surface is not an accessible focus cue.
            # Preserve its bright border for keyboard focus and selected tabs.
            tokens['focus'] = tokens['border']
            tokens['accent'] = tokens['border']
            tokens['selection'] = tokens['border']
        else:
            tokens['focus'] = _contrasting_surface(tokens['accent'], reference_surface, 3.0)

        # Text/icons are rendered opaque over translucent control fills. Test
        # them against the *composited* normal, hover and checked surfaces—not
        # merely the source theme color. This is the key distinction for image
        # backgrounds and low control-opacity values.
        if background_active:
            effective_control_surface = _mix_colors(
                reference_surface, tokens['control_surface'], self.control_opacity
            )
            effective_control_hover = _mix_colors(
                reference_surface, tokens['control_hover'],
                min(1.0, self.control_opacity + 0.08),
            )
            effective_panel_surface = _mix_colors(
                reference_surface, tokens['surface'], self.control_opacity
            )
        else:
            effective_control_surface = tokens['control_surface']
            effective_control_hover = tokens['control_hover']
            effective_panel_surface = tokens['canvas']

        control_text = _readable_color(
            tokens['control_text'], effective_control_surface, 4.5
        )
        if _contrast_ratio(control_text, effective_control_hover) < 4.5:
            # An icon cannot recolor itself through QSS. Keep the hover fill on
            # the same luminance side and communicate hover via the focus
            # border, rather than making the icon disappear mid-interaction.
            tokens['control_hover'] = tokens['control_surface']
            effective_control_hover = effective_control_surface
        tokens['control_text'] = control_text
        # Checked/active buttons retain their readable surface and use the
        # accent as an opaque border. This preserves both icon contrast and a
        # redundant non-color state cue.
        effective_accent_surface = effective_control_surface
        tokens['accent_text'] = _readable_color(
            tokens.get('accent_text', control_text), tokens['accent'], 4.5
        )
        tokens['panel_text'] = _readable_color(
            tokens.get('muted', tokens['text']), effective_panel_surface, 4.5
        )
        tokens['rail_surface'] = (
            tokens['control_surface'] if background_active else tokens['canvas']
        )
        tokens['rail_hover'] = tokens['control_hover']
        tokens['rail_checked'] = tokens['rail_surface']
        tokens['rail_text'] = _readable_color(
            tokens['control_text'], tokens['rail_surface'], 4.5
        )
        if _contrast_ratio(tokens['rail_text'], tokens['rail_hover']) < 4.5:
            tokens['rail_hover'] = tokens['rail_surface']
        tokens['effective_control_surface'] = effective_control_surface
        tokens['effective_control_hover'] = effective_control_hover
        tokens['effective_accent_surface'] = effective_accent_surface
        tokens['effective_panel_surface'] = effective_panel_surface
        tokens['border'] = _contrasting_surface(tokens['border'], reference_surface, 3.0)
        tokens['input_border'] = tokens['border']
        tokens['title_border'] = _contrasting_surface(
            theme_title_border, reference_surface, 3.0
        )
        tokens['selection'] = tokens['accent']
        tokens['selection_text'] = tokens['accent_text']
        tokens['muted'] = _readable_color(tokens['muted'], reference_surface, 4.5)

        # Refresh compatibility aliases after all theme/user overrides.
        tokens.update({
            'separator_color': tokens['muted'], 'bg': tokens['control_surface'],
            'color': tokens['control_text'], 'hover_bg': tokens['control_hover'],
            'pressed_bg': tokens['border'], 'checked_bg': tokens['accent'],
            'checked_color': tokens['accent_text'], 'focus_border': tokens['focus'],
            'panel_bg': tokens['canvas'], 'input_bg': tokens['surface'],
            'card_start': tokens['surface'], 'card_end': tokens['surface_alt'],
            'accent_start': tokens['accent'], 'accent_end': tokens['accent'],
            'title_start': tokens['title_surface'], 'title_end': tokens['title_surface'],
        })
        tokens['title_alpha'] = _rgba_for_hex(tokens['title_surface'], self.control_opacity)
        tokens['editor_alpha'] = _rgba_for_hex(tokens['editor_bg'], self.control_opacity)
        tokens['control_alpha'] = _rgba_for_hex(tokens['control_surface'], self.control_opacity)
        tokens['control_hover_alpha'] = _rgba_for_hex(
            tokens['control_hover'], min(1.0, self.control_opacity + 0.08)
        )
        tokens['panel_alpha'] = _rgba_for_hex(tokens['surface'], self.control_opacity)
        tokens['accent_alpha'] = _rgba_for_hex(tokens['accent'], self.control_opacity)
        return tokens

    def apply_adaptive_control_styles(self, styles):
        background_active = self._has_background_image()
        chrome_text = styles['panel_text'] if background_active else styles['separator_color']
        # 分隔符标签样式
        for sep in ['separator1', 'separator2', 'separator3', 'separator4',
                     'separator5', 'separator6', 'separator7']:
            if hasattr(self, sep):
                getattr(self, sep).setStyleSheet(f'color: {chrome_text}; margin: 0 5px;')
        for label_name in ('transparency_label', 'control_opacity_label'):
            if hasattr(self, label_name):
                getattr(self, label_name).setStyleSheet(
                    f'color: {chrome_text}; margin: 0 5px; font-weight: 500;'
                )
        if hasattr(self, 'version_label'):
            self.version_label.setStyleSheet(
                f'color: {chrome_text}; font-size: 7pt; '
                'background: transparent; border: none;'
            )
        for checkbox_name in ('topmost_checkbox', 'format_checkbox'):
            checkbox = getattr(self, checkbox_name, None)
            if checkbox is not None:
                checkbox.setStyleSheet(f'''
                    QCheckBox {{
                        color: {chrome_text}; background: transparent;
                        spacing: 6px; padding: 2px 4px;
                    }}
                    QCheckBox:focus {{
                        border: 1px solid {styles['focus']};
                        border-radius: 4px;
                    }}
                ''')

        # 通用按钮模板
        button_styles = dict(styles)
        button_styles.update({
            'button_bg': styles['control_alpha'] if background_active else styles['control_surface'],
            'button_hover': styles['control_hover_alpha'] if background_active else styles['control_hover'],
            'button_text': styles['control_text'],
            'checked_surface': styles['control_alpha'] if background_active else styles['control_surface'],
        })
        button_template = '''
            QPushButton {{
                background-color: {button_bg}; color: {button_text};
                border: 1px solid {border}; border-radius: {radius_control}px;
                font-weight: 600; padding: 0 7px; min-height: 28px;
            }}
            QPushButton[compactToolButton="true"] {{ padding: 0 4px; }}
            QPushButton:hover {{ background-color: {button_hover}; border-color: {focus}; }}
            QPushButton:pressed {{
                background-color: {button_hover}; border: 2px solid {focus};
            }}
            QPushButton:focus {{ border: 2px solid {focus}; }}
            QPushButton:checked {{
                background-color: {checked_surface}; color: {button_text}; border: 2px solid {accent};
            }}
            QPushButton#reminderButton[reminderActive="true"] {{
                background-color: {checked_surface}; color: {button_text}; border: 2px solid {accent};
            }}
            QPushButton#deleteButton {{
                background-color: transparent; color: {danger}; border-color: {danger_border};
            }}
            QPushButton#deleteButton:hover {{ background-color: {danger}; color: {accent_text}; border-color: {danger}; }}
            QPushButton:disabled {{ color: {muted}; background-color: transparent; border-color: {border}; }}
        '''
        base_style = button_template.format(**button_styles)

        if hasattr(self, 'tool_rail_buttons'):
            rail_tab_style = f'''
                QPushButton {{
                    background: {styles['rail_surface']};
                    color: {styles['rail_text']};
                    border: 1px solid {styles['border']};
                    border-radius: 6px; font-weight: 600; padding: 0;
                }}
                QPushButton:hover {{
                    background: {styles['rail_hover']};
                    border-color: {styles['focus']};
                }}
                QPushButton:focus {{ border: 2px solid {styles['focus']}; }}
                QPushButton:checked {{
                    background: {styles['rail_checked']};
                    border: 2px solid {styles['accent']};
                }}
            '''
            for button in self.tool_rail_buttons:
                button.setStyleSheet(rail_tab_style)
                button.setIcon(_make_vector_icon(
                    button.property('toolRailIcon'), styles['rail_text'],
                    monochrome=self._has_background_image()
                ))
                button.setIconSize(QSize(20, 20))

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
            italic_style = button_template.replace('font-weight: bold;', 'font-weight: bold; font-style: italic;').format(**button_styles)
            self.italic_btn.setStyleSheet(italic_style)

        # 字体颜色按钮使用所选颜色绘制图标，按钮状态仍遵循同一套令牌。
        if hasattr(self, 'color_btn'):
            self.color_btn.setStyleSheet(base_style)
            selected_color = (
                self.font_color if self.font_color_mode == 'manual'
                else styles['control_text'] if background_active else styles['text']
            )
            self.color_btn.setIcon(_make_vector_icon(
                'font_color', selected_color, monochrome=background_active
            ))

        # 功能按钮（撤销/重做/标签/提醒/锁定/链接/图片/MD/反链/删除/帮助/隐藏）
        for btn in ['undo_btn', 'redo_btn', 'tag_btn', 'reminder_btn',
                     'lock_btn', 'link_btn', 'image_btn', 'md_toggle_btn',
                     'backlink_btn', 'help_btn', 'hide_btn', 'background_btn',
                     'clear_background_btn', 'background_text_color_btn',
                     'background_control_color_btn', 'reset_background_colors_btn']:
            if hasattr(self, btn):
                getattr(self, btn).setStyleSheet(base_style)

        # 删除按钮特殊样式（红色调）
        if hasattr(self, 'delete_btn'):
            danger_style = base_style
            self.delete_btn.setStyleSheet(danger_style)

        # Text fields and the two horizontally scrollable action strips use a
        # consistent visual hierarchy.  Object names keep these rules local to
        # the note window and avoid changing dialogs opened by the app.
        if hasattr(self, 'title_edit'):
            self.title_edit.setStyleSheet(f'''
                QLineEdit#noteTitle {{
                    background-color: {styles['title_alpha'] if background_active else styles['title_surface']};
                    color: {styles['title_text']};
                    border: 1px solid {styles['title_border']};
                    border-radius: {styles['radius_field']}px;
                    padding: 0 13px;
                    font-weight: 700;
                    selection-background-color: {styles['selection']};
                    selection-color: {styles['selection_text']};
                }}
                QLineEdit#noteTitle:hover {{ border-color: {styles['focus_border']}; }}
                QLineEdit#noteTitle:focus {{ border: 2px solid {styles['focus_border']}; }}
            ''')
        if hasattr(self, 'text_edit'):
            self.text_edit.setStyleSheet(f'''
                QTextEdit {{
                    background-color: {styles['editor_alpha'] if background_active else styles['editor_bg']};
                    color: {styles['text']};
                    border: 1px solid {styles['input_border']};
                    border-radius: {styles['radius_field']}px;
                    padding: 12px;
                    selection-background-color: {styles['selection']};
                    selection-color: {styles['selection_text']};
                }}
                QTextEdit:hover {{ border-color: {styles['focus_border']}; }}
                QTextEdit:focus {{ border: 2px solid {styles['focus_border']}; }}
            ''')
        if hasattr(self, 'format_scroll'):
            panel_border = (
                f'border: 1px solid {styles["border"]}; border-radius: 8px;'
                if background_active else
                f'border-top: 1px solid {styles["border"]}; border-radius: 0;'
            )
            strip_style = f'''
                QScrollArea#formatScroll, QScrollArea#settingsScroll,
                QScrollArea#actionScroll {{
                    background: transparent; border: none;
                }}
                QWidget#formatPanel, QWidget#settingsPanel, QWidget#actionPanel {{
                    background: transparent;
                }}
                QFrame#controlPanel {{
                    background: {styles['panel_alpha'] if background_active else styles['canvas']};
                    {panel_border}
                }}
                QFrame[toolGroup="true"] {{
                    background-color: {styles['panel_alpha'] if background_active else styles['surface']};
                    border: 1px solid {styles['border']};
                    border-radius: 9px;
                }}
                QFrame#toolRailNav {{
                    background-color: {styles['panel_alpha'] if background_active else styles['surface_alt']};
                }}
                QFrame#actionDangerGroup {{ border-color: {styles['danger_border']}; }}
                QScrollArea#formatScroll QScrollBar:horizontal,
                QScrollArea#settingsScroll QScrollBar:horizontal,
                QScrollArea#actionScroll QScrollBar:horizontal {{
                    height: 10px; background: transparent;
                }}
                QScrollArea#formatScroll QScrollBar::handle:horizontal,
                QScrollArea#settingsScroll QScrollBar::handle:horizontal,
                QScrollArea#actionScroll QScrollBar::handle:horizontal {{
                    background: {styles['border']}; border-radius: 3px; min-width: 34px;
                }}
                QScrollArea#formatScroll QScrollBar::handle:horizontal:hover,
                QScrollArea#settingsScroll QScrollBar::handle:horizontal:hover,
                QScrollArea#actionScroll QScrollBar::handle:horizontal:hover {{
                    background: {styles['focus']};
                }}
                QScrollArea#formatScroll QScrollBar::add-line:horizontal,
                QScrollArea#formatScroll QScrollBar::sub-line:horizontal,
                QScrollArea#settingsScroll QScrollBar::add-line:horizontal,
                QScrollArea#settingsScroll QScrollBar::sub-line:horizontal,
                QScrollArea#actionScroll QScrollBar::add-line:horizontal,
                QScrollArea#actionScroll QScrollBar::sub-line:horizontal {{ width: 0; }}
            '''
            self.format_scroll.setStyleSheet(strip_style)
            self.settings_scroll.setStyleSheet(strip_style)
            self.action_scroll.setStyleSheet(strip_style)
            self.control_panel.setStyleSheet(strip_style)
        self._prepare_action_icons(styles['control_text'])

    @staticmethod
    def _get_extra_theme_css(is_dark):
        """生成所有主题通用的补充 CSS（QScrollBar、Slider groove、QStackedWidget 等）"""
        # New callers pass the semantic style map.  The boolean branch below
        # remains as a compatibility fallback for external integrations.
        if isinstance(is_dark, dict):
            styles = is_dark
            return f'''
                QWidget#formatPanel, QWidget#settingsPanel, QWidget#actionPanel {{ background: transparent; }}
                QScrollArea#formatScroll, QScrollArea#settingsScroll,
                QScrollArea#actionScroll {{ background: transparent; border: none; }}
                QScrollArea#formatScroll QScrollBar:horizontal,
                QScrollArea#settingsScroll QScrollBar:horizontal,
                QScrollArea#actionScroll QScrollBar:horizontal {{ height: 10px; background: transparent; }}
                QScrollArea#formatScroll QScrollBar::handle:horizontal,
                QScrollArea#settingsScroll QScrollBar::handle:horizontal,
                QScrollArea#actionScroll QScrollBar::handle:horizontal {{
                    background: {styles['border']}; border-radius: 3px; min-width: 34px;
                }}
                QScrollArea#formatScroll QScrollBar::add-line:horizontal,
                QScrollArea#formatScroll QScrollBar::sub-line:horizontal,
                QScrollArea#settingsScroll QScrollBar::add-line:horizontal,
                QScrollArea#settingsScroll QScrollBar::sub-line:horizontal,
                QScrollArea#actionScroll QScrollBar::add-line:horizontal,
                QScrollArea#actionScroll QScrollBar::sub-line:horizontal {{ width: 0; }}
                QScrollBar:vertical {{ background: transparent; width: 10px; border: none; }}
                QScrollBar::handle:vertical {{
                    background: {styles['border']}; border-radius: 5px; min-height: 30px;
                }}
                QScrollBar::handle:vertical:hover {{ background: {styles['muted']}; }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
                QScrollBar:horizontal {{ background: transparent; height: 10px; border: none; }}
                QScrollBar::handle:horizontal {{
                    background: {styles['border']}; border-radius: 5px; min-width: 30px;
                }}
                QScrollBar::handle:horizontal:hover {{ background: {styles['muted']}; }}
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
                QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
                QSlider::groove:horizontal {{
                    background: {styles['border']}; height: 5px; border-radius: 2px;
                }}
                QSlider::sub-page:horizontal {{ background: {styles['accent']}; border-radius: 2px; }}
                QSlider::handle:horizontal {{
                    background: {styles['surface']}; border: 2px solid {styles['accent']};
                    width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
                }}
                QStackedWidget {{ background: transparent; border: none; }}
                QLabel {{ background: transparent; }}
            '''
        if is_dark:
            return '''
                QWidget#formatPanel, QWidget#settingsPanel, QWidget#actionPanel { background: transparent; }
                QScrollArea#formatScroll, QScrollArea#settingsScroll,
                QScrollArea#actionScroll { background: transparent; border: none; }
                QScrollArea#formatScroll QScrollBar:horizontal,
                QScrollArea#settingsScroll QScrollBar:horizontal,
                QScrollArea#actionScroll QScrollBar:horizontal { height: 10px; background: transparent; }
                QScrollArea#formatScroll QScrollBar::handle:horizontal,
                QScrollArea#settingsScroll QScrollBar::handle:horizontal,
                QScrollArea#actionScroll QScrollBar::handle:horizontal { background: #64748B; border-radius: 3px; min-width: 34px; }
                QScrollArea#formatScroll QScrollBar::add-line:horizontal,
                QScrollArea#formatScroll QScrollBar::sub-line:horizontal,
                QScrollArea#settingsScroll QScrollBar::add-line:horizontal,
                QScrollArea#settingsScroll QScrollBar::sub-line:horizontal,
                QScrollArea#actionScroll QScrollBar::add-line:horizontal,
                QScrollArea#actionScroll QScrollBar::sub-line:horizontal { width: 0; }
                QScrollBar:vertical {
                    background: transparent; width: 10px; border: none;
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
                    background: #334155; height: 6px; border-radius: 3px;
                }
                QSlider::sub-page:horizontal { background: #3B82F6; border-radius: 3px; }
                QSlider::handle:horizontal { background: #DBEAFE; border: 2px solid #3B82F6; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
                QStackedWidget { background: transparent; border: none; }
                QTextBrowser {
                    background-color: #2b2b2b; color: #e0e0e0; border: 1px solid #555;
                }
                QLabel { background: transparent; }
            '''
        else:
            return '''
                QWidget#formatPanel, QWidget#settingsPanel, QWidget#actionPanel { background: transparent; }
                QScrollArea#formatScroll, QScrollArea#settingsScroll,
                QScrollArea#actionScroll { background: transparent; border: none; }
                QScrollArea#formatScroll QScrollBar:horizontal,
                QScrollArea#settingsScroll QScrollBar:horizontal,
                QScrollArea#actionScroll QScrollBar:horizontal { height: 10px; background: transparent; }
                QScrollArea#formatScroll QScrollBar::handle:horizontal,
                QScrollArea#settingsScroll QScrollBar::handle:horizontal,
                QScrollArea#actionScroll QScrollBar::handle:horizontal { background: #CBD5E1; border-radius: 3px; min-width: 34px; }
                QScrollArea#formatScroll QScrollBar::add-line:horizontal,
                QScrollArea#formatScroll QScrollBar::sub-line:horizontal,
                QScrollArea#settingsScroll QScrollBar::add-line:horizontal,
                QScrollArea#settingsScroll QScrollBar::sub-line:horizontal,
                QScrollArea#actionScroll QScrollBar::add-line:horizontal,
                QScrollArea#actionScroll QScrollBar::sub-line:horizontal { width: 0; }
                QScrollBar:vertical {
                    background: transparent; width: 10px; border: none;
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
                    background: #E2E8F0; height: 6px; border-radius: 3px;
                }
                QSlider::sub-page:horizontal { background: #3B82F6; border-radius: 3px; }
                QSlider::handle:horizontal { background: #EFF6FF; border: 2px solid #3B82F6; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
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
            adaptive_styles = self._theme_tokens_from_css(style, is_dark)
            self._current_theme_styles = adaptive_styles
            # 追加通用补充 CSS（QScrollBar / QSlider groove / QStackedWidget 等）
            extra_css = self._get_extra_theme_css(adaptive_styles)
            # Give the frameless note a soft card silhouette while retaining
            # the palette supplied by each user-selectable theme.
            # The top-level surface is painted by ``paintEvent``.  Keeping the
            # root background transparent prevents QSS from filling the native
            # rectangular corners before the rounded path is composited.
            full_style = style + extra_css + (
                '\nStickyNote { background: transparent; '
                'background-color: transparent; border: none; '
                f'border-radius: {self.WINDOW_CORNER_RADIUS}px; }}'
            )
            self.setStyleSheet(full_style)
            self.text_edit.setStyleSheet(full_style)
            self.title_edit.setStyleSheet(full_style)
            self.apply_adaptive_control_styles(adaptive_styles)
            self._refresh_hide_tab_style()
            # md_preview 根据深色/浅色主题设置独立样式
            if hasattr(self, 'md_preview'):
                md_bg = adaptive_styles['surface']
                md_border = adaptive_styles['border']
                md_text = adaptive_styles['text']
                self.md_preview.setStyleSheet(f'''
                    QTextBrowser {{
                        background-color: {md_bg};
                        color: {md_text};
                        border: 1px solid {md_border};
                    }}
                ''')
            # 更新边框画笔颜色以匹配主题
            self._border_pen.setColor(QColor(adaptive_styles['border']))
            if hasattr(self, 'font_settings') and self.font_settings:
                self.apply_font()
        except Exception as e:
            print(f'[StickyNote] 加载样式文件失败: {theme_css_file} - {e}')
            self._apply_default_style()

    def _apply_default_style(self):
        """应用硬编码的默认回退样式"""
        default_style = '''
            StickyNote { background-color: #FFF9C4; border-radius: 12px; }
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
            StickyNote { background: transparent; background-color: transparent;
                         border: none; border-radius: 12px; }
        '''
        self.setStyleSheet(default_style)
        self.text_edit.setStyleSheet(default_style)
        self.title_edit.setStyleSheet(default_style)
        is_dark = self.is_dark_theme(default_style)
        adaptive_styles = self._theme_tokens_from_css(default_style, is_dark)
        self._current_theme_styles = adaptive_styles
        self.apply_adaptive_control_styles(adaptive_styles)
        self._refresh_hide_tab_style()
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
        self._border_pen.setColor(QColor(adaptive_styles['border']))
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
        font_style_sheet = f'''
            font-family: "{font_family}" !important;
            font-size: {font_size}pt !important;
            font-weight: {font_weight} !important;
            font-style: {font_style} !important;
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
        text_char_format = QTextCharFormat()
        if font_settings:
            font = QFont()
            font.setFamily(font_settings.get('family', '\u5fae\u8f6f\u96c5\u9ed1'))
            font.setPointSize(font_settings.get('size', 12))
            font.setBold(font_settings.get('bold', False))
            font.setItalic(font_settings.get('italic', False))
            text_char_format.setFont(font)
        if self.font_color_mode == 'manual':
            text_char_format.setForeground(QColor(self.font_color))
        self.text_edit.setCurrentCharFormat(text_char_format)
        title_palette = self.title_edit.palette()
        effective_title_color = getattr(self, '_current_theme_styles', {}).get(
            'title_text', '#333333'
        )
        title_palette.setColor(QPalette.Text, QColor(effective_title_color))
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
            'background_image': '',
            'control_opacity': 1.0,
            'background_text_color': '',
            'background_control_color': '',
            'title_font_size': 12,
            'content_font_size': 12,
            'auto_format_enabled': True,
            'font_color': '#000000',
            'font_color_mode': 'theme',
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
        self.note_data['background_image'] = self.background_image
        self.note_data['control_opacity'] = self.control_opacity
        self.note_data['background_text_color'] = self.background_text_color
        self.note_data['background_control_color'] = self.background_control_color
        self.note_data['font_color'] = self.font_color
        self.note_data['font_color_mode'] = self.font_color_mode
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
        # Keep the icon-led presentation consistent after state changes.  The
        # accessible name and tooltip carry the text label for assistive tech.
        self.lock_btn.setText('')
        self.lock_btn.setIcon(_make_vector_icon(
            'lock' if self.is_locked else 'unlock', self._current_icon_color(),
            monochrome=self._has_background_image(),
        ))
        self.lock_btn.setIconSize(QSize(19, 19))
        self.lock_btn.setAccessibleName('解锁便签' if self.is_locked else '锁定便签')
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
        self.reminder_btn.setIcon(_make_vector_icon(
            'bell', self._current_icon_color(),
            monochrome=self._has_background_image(),
        ))
        self.reminder_btn.setIconSize(QSize(19, 19))
        self.reminder_btn.setText('')
        self.reminder_btn.setAccessibleName('设置提醒')
        if info['enabled']:
            self.reminder_btn.setToolTip(info['text'])
            self.reminder_btn.setProperty('reminderActive', True)
            self.reminder_btn.style().unpolish(self.reminder_btn)
            self.reminder_btn.style().polish(self.reminder_btn)
        else:
            self.reminder_btn.setToolTip('设置提醒')
            self.reminder_btn.setProperty('reminderActive', False)
            self.reminder_btn.style().unpolish(self.reminder_btn)
            self.reminder_btn.style().polish(self.reminder_btn)

    # ==================== 窗口拖拽和调整大小 ====================

    def mousePressEvent(self, event):
        # 自动隐藏状态下不响应鼠标事件（防止边缘残留触发拖拽/缩放）
        if self.auto_hidden:
            return
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
        # 自动隐藏状态下不响应鼠标事件（防止边缘残留触发缩放）
        if self.auto_hidden:
            self.setCursor(QCursor(Qt.ArrowCursor))
            return
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
    HIDE_TAB_WIDTH = 144
    HIDE_TAB_HEIGHT = 34

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

        title = self.title_edit.text().strip() if hasattr(self, 'title_edit') else ''
        title = title or self.note_data.get('title', f'便签 {self.note_id}')
        short_title = title[:9] + ('…' if len(title) > 9 else '')

        self.hide_tab = QWidget(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.hide_tab.setObjectName('hideTab')
        self.hide_tab.setFixedSize(self.HIDE_TAB_WIDTH, self.HIDE_TAB_HEIGHT)
        self.hide_tab.setMouseTracking(True)
        self.hide_tab.setAttribute(Qt.WA_StyledBackground, True)
        self.hide_tab.setCursor(QCursor(Qt.PointingHandCursor))
        self.hide_tab.setFocusPolicy(Qt.StrongFocus)
        self.hide_tab.setAccessibleName(f'隐藏便签：{title}，单击展开')
        self.hide_tab.setToolTip('悬停预览便签，单击后保持展开')

        # Reuse the resolved semantic theme rather than guessing from a stale
        # dark-mode flag. The handle remains opaque even when the note uses an
        # image so it is always discoverable at the screen edge.
        styles = getattr(self, '_current_theme_styles', {})
        bg = styles.get('surface', '#FFFDE7')
        hover_bg = styles.get('surface_alt', bg)
        border = styles.get('border', '#8A7D22')
        focus = styles.get('focus', border)
        accent = styles.get('accent', border)
        accent_text = _readable_color(styles.get('accent_text'), accent, 4.5)
        fg = _readable_color(styles.get('text'), bg, 4.5)

        self.hide_tab.setStyleSheet(f'''
            QWidget#hideTab {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 9px;
            }}
            QWidget#hideTab:hover, QWidget#hideTab:focus {{
                background-color: {hover_bg};
                border: 2px solid {focus};
            }}
            QLabel#hideTabIcon {{
                background-color: {accent};
                border: none;
                border-radius: 8px;
            }}
            QLabel#hideTabTitle {{
                color: {fg};
                background: transparent;
                border: none;
                font-size: 9pt;
                font-weight: 600;
            }}
        ''')

        layout = QHBoxLayout()
        layout.setContentsMargins(5, 4, 8, 4)
        layout.setSpacing(7)

        # A stable vector edge/restore glyph replaces the platform-dependent
        # triangle character shown in the legacy handle.
        icon_map = {
            'left': 'edge_right', 'right': 'edge_left',
            'top': 'edge_down', 'bottom': 'edge_up',
        }
        icon_label = QLabel()
        icon_label.setObjectName('hideTabIcon')
        icon_label.setFixedSize(24, 24)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        icon_label.setPixmap(
            _make_vector_icon(
                icon_map.get(self.hidden_edge, 'edge_right'),
                accent_text, size=18, monochrome=True,
            ).pixmap(18, 18)
        )
        layout.addWidget(icon_label)

        title_label = QLabel(short_title)
        title_label.setObjectName('hideTabTitle')
        title_label.setToolTip(title)
        title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(title_label)
        layout.addStretch()

        self.hide_tab.setLayout(layout)

        # 安装事件过滤器以检测悬停和点击
        self.hide_tab.installEventFilter(self)

    def _refresh_hide_tab_style(self):
        """Refresh an existing edge handle after a theme change."""
        if self.hide_tab is None:
            return
        styles = getattr(self, '_current_theme_styles', {})
        bg = styles.get('surface', '#FFFDE7')
        hover_bg = styles.get('surface_alt', bg)
        border = styles.get('border', '#8A7D22')
        focus = styles.get('focus', border)
        accent = styles.get('accent', border)
        accent_text = _readable_color(styles.get('accent_text'), accent, 4.5)
        fg = _readable_color(styles.get('text'), bg, 4.5)
        self.hide_tab.setStyleSheet(f'''
            QWidget#hideTab {{
                background-color: {bg}; border: 1px solid {border};
                border-radius: 9px;
            }}
            QWidget#hideTab:hover, QWidget#hideTab:focus {{
                background-color: {hover_bg}; border: 2px solid {focus};
            }}
            QLabel#hideTabIcon {{
                background-color: {accent}; border: none; border-radius: 8px;
            }}
            QLabel#hideTabTitle {{
                color: {fg}; background: transparent; border: none;
                font-size: 9pt; font-weight: 600;
            }}
        ''')
        icon_label = self.hide_tab.findChild(QLabel, 'hideTabIcon')
        if icon_label is not None:
            icon_map = {
                'left': 'edge_right', 'right': 'edge_left',
                'top': 'edge_down', 'bottom': 'edge_up',
            }
            icon_label.setPixmap(
                _make_vector_icon(
                    icon_map.get(self.hidden_edge, 'edge_right'),
                    accent_text, size=18, monochrome=True,
                ).pixmap(18, 18)
            )

    def _position_hide_tab(self):
        """根据隐藏边缘计算标签页的屏幕位置"""
        if self.hide_tab is None:
            return

        desktop = QApplication.desktop()
        if not desktop:
            return
        screen = self._get_screen_geometry()
        pre_geo = self._pre_hide_geometry
        tab_w, tab_h = self.HIDE_TAB_WIDTH, self.HIDE_TAB_HEIGHT

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
        """便签主窗口滑出屏幕的动画（完全移出屏幕，不残留任何像素）"""
        desktop = QApplication.desktop()
        if not desktop:
            return
        screen = self._get_screen_geometry()
        current_pos = self.pos()
        w, h = self.width(), self.height()

        if edge == 'left':
            target = QPoint(screen.left() - w, current_pos.y())
        elif edge == 'right':
            target = QPoint(screen.right() + 1, current_pos.y())
        elif edge == 'top':
            target = QPoint(current_pos.x(), screen.top() - h)
        else:  # bottom
            target = QPoint(current_pos.x(), screen.bottom() + 1)

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
            elif event.type() == QEvent.KeyPress and event.key() in (
                    Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                self._restore_from_auto_hide(hover_triggered=False)
                return True
        return super().eventFilter(obj, event)

    def perform_resize(self, global_pos):
        delta = global_pos - self.drag_pos
        geometry = QRect(self.initial_geometry)
        # Keep interactive resizing consistent with QWidget's declared
        # minimum (240x240); the previous hard-coded 100x120 bypassed that
        # contract and could make the editor/tool rail unreachable.
        min_width = max(1, self.minimumWidth())
        min_height = max(1, self.minimumHeight())
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
        painter.setRenderHint(QPainter.Antialiasing, True)
        # Clear the backing store explicitly.  This is important for a
        # translucent top-level widget: a previous rectangular frame must not
        # survive after a resize or a background-image change.
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # The exact path is also converted to the native QRegion mask in
        # ``_update_window_shape``.  Do not maintain separate radii/rectangles
        # for paint and hit testing.
        rounded_path = self._rounded_window_path()
        if rounded_path.isEmpty():
            painter.end()
            return

        styles = getattr(self, '_current_theme_styles', {})
        surface_color = styles.get('canvas', '#FFF9C4')
        painter.save()
        painter.setClipPath(rounded_path)
        painter.fillPath(rounded_path, QBrush(QColor(surface_color)))

        if not self._background_pixmap.isNull():
            target = self.rect()
            try:
                current_dpr = float(self.devicePixelRatioF())
            except (AttributeError, TypeError, ValueError):
                current_dpr = 1.0
            cache_stale = (
                self._background_scaled_size != target.size() or
                abs(getattr(self, '_background_scaled_dpr', 1.0) - current_dpr) > 0.01
            )
            if cache_stale:
                source = self._background_pixmap
                if source.width() > 0 and source.height() > 0:
                    scale = max(
                        target.width() / source.width(),
                        target.height() / source.height(),
                    )
                    scaled = source.scaled(
                        max(1, int(source.width() * scale)),
                        max(1, int(source.height() * scale)),
                        Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
                    )
                    self._background_scaled_cache = scaled
                    self._background_scaled_size = target.size()
                    self._background_scaled_dpr = current_dpr
            scaled = self._background_scaled_cache
            if not scaled.isNull():
                x = max(0, (scaled.width() - target.width()) // 2)
                y = max(0, (scaled.height() - target.height()) // 2)
                painter.drawPixmap(
                    target, scaled,
                    QRect(x, y, target.width(), target.height()),
                )
        painter.restore()

        painter.setPen(self._border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(rounded_path)

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

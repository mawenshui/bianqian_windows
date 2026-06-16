# -*- coding: utf-8 -*-
"""
主题全局适配模块

为所有对话框（搜索、备份、设置等）提供深色/浅色主题自动适配，
保持与便签窗口一致的视觉风格。
"""

import os
import re
import logging
from typing import Optional

from PyQt5.QtCore import QFileSystemWatcher

from core import get_styles_dir

logger = logging.getLogger(__name__)

# 缓存已解析的主题 CSS
_theme_cache: dict = {}

# 全局文件系统监视器（单例，共享给所有调用者）
_theme_watcher: Optional[QFileSystemWatcher] = None


def invalidate_cache():
    """清空主题 CSS 缓存，强制下次重新加载"""
    _theme_cache.clear()
    logger.debug('主题缓存已清空')


def setup_theme_watcher(styles_dir: str, on_changed_callback) -> QFileSystemWatcher:
    """
    初始化主题文件监视器，监听 styles 目录中的 CSS 文件变更。
    
    Args:
        styles_dir: styles 目录路径
        on_changed_callback: 文件变更时的回调函数
        
    Returns:
        QFileSystemWatcher 实例
    """
    global _theme_watcher
    if _theme_watcher is not None:
        return _theme_watcher
    
    _theme_watcher = QFileSystemWatcher()
    if os.path.exists(styles_dir):
        _theme_watcher.addPath(styles_dir)
        # 监听目录中已有的 CSS 文件
        for fname in os.listdir(styles_dir):
            if fname.endswith('.css'):
                _theme_watcher.addPath(os.path.join(styles_dir, fname))
    _theme_watcher.directoryChanged.connect(lambda path: _on_dir_changed(path, on_changed_callback))
    _theme_watcher.fileChanged.connect(lambda path: _on_file_changed(path, on_changed_callback))
    logger.debug('主题文件监视器已启动')
    return _theme_watcher


def _on_dir_changed(dir_path, callback):
    """styles 目录变化（新增/删除文件）"""
    global _theme_watcher
    if _theme_watcher and os.path.exists(dir_path):
        for fname in os.listdir(dir_path):
            fpath = os.path.join(dir_path, fname)
            if fname.endswith('.css') and fpath not in _theme_watcher.files():
                _theme_watcher.addPath(fpath)
    invalidate_cache()
    if callback:
        callback()


def _on_file_changed(file_path, callback):
    """单个 CSS 文件内容变更"""
    invalidate_cache()
    if callback:
        callback()


def _load_theme_css(css_filename: str) -> str:
    """加载指定主题的 CSS 内容（带缓存）"""
    if css_filename in _theme_cache:
        return _theme_cache[css_filename]
    css_path = os.path.join(get_styles_dir(), css_filename)
    if os.path.exists(css_path):
        try:
            with open(css_path, 'r', encoding='utf-8') as f:
                content = f.read()
            _theme_cache[css_filename] = content
            return content
        except Exception as e:
            logger.warning(f'加载主题 CSS 失败: {e}')
    return ''


def is_dark_theme_css(css_content: str) -> bool:
    """检测 CSS 内容是否为深色主题（基于背景色亮度计算）"""
    bg_match = re.search(r'StickyNote\s*\{[^}]*background-color:\s*([^;]+);', css_content)
    if bg_match:
        bg_color = bg_match.group(1).strip()
        # 尝试解析 hex 颜色
        hex_match = re.match(r'#([0-9a-fA-F]{3,8})', bg_color)
        if hex_match:
            hex_str = hex_match.group(1)
            if len(hex_str) == 3:
                r, g, b = int(hex_str[0]*2, 16), int(hex_str[1]*2, 16), int(hex_str[2]*2, 16)
            elif len(hex_str) >= 6:
                r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
            else:
                return False
            # 使用 W3C 相对亮度公式: L = 0.2126*R + 0.7152*G + 0.0722*B
            luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
            return luminance < 0.5
        # 回退到关键词检测
        dark_keywords = ['#2', '#3', '#4', '#5', 'black', 'dark']
        return any(k in bg_color.lower() for k in dark_keywords)
    return False


def _extract_color(css_content: str, selector: str, prop: str, fallback: str) -> str:
    """从 CSS 内容中提取指定选择器和属性的颜色值"""
    pattern = rf'{re.escape(selector)}\s*\{{[^}}]*{re.escape(prop)}:\s*([^;]+);'
    match = re.search(pattern, css_content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return fallback


def generate_dialog_stylesheet(css_filename: str) -> str:
    """
    根据便签主题 CSS 生成适用于 QDialog 的样式表。

    Args:
        css_filename: 主题 CSS 文件名（如 'soft_yellow.css'）

    Returns:
        适用于 QDialog 的完整样式表字符串
    """
    css_content = _load_theme_css(css_filename)
    if not css_content:
        return _fallback_dialog_style(False)

    dark = is_dark_theme_css(css_content)

    # 从便签 CSS 中提取主色调
    bg_color = _extract_color(css_content, 'StickyNote', 'background-color',
                              '#2b2b2b' if dark else '#FFFFCC')
    text_color = _extract_color(css_content, 'StickyNote', 'color',
                                '#e0e0e0' if dark else '#000000')
    btn_bg = _extract_color(css_content, 'QPushButton', 'background-color',
                            '#555555' if dark else '#F0F0F0')
    btn_color = _extract_color(css_content, 'QPushButton', 'color',
                               '#ffffff' if dark else '#000000')
    input_bg = _extract_color(css_content, 'QLineEdit', 'background-color',
                              '#3c3c3c' if dark else '#FFFFFF')
    input_border = _extract_color(css_content, 'QLineEdit', 'border',
                                  '1px solid #555' if dark else '1px solid #ccc')

    if dark:
        return f"""
            QDialog {{
                background-color: {bg_color};
                color: {text_color};
            }}
            QLabel {{
                color: {text_color};
                background: transparent;
            }}
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_color};
                border: 1px solid #666;
                border-radius: 4px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{
                background-color: #666666;
            }}
            QPushButton:pressed {{
                background-color: #777777;
            }}
            QPushButton:disabled {{
                color: #888;
                background-color: #444;
            }}
            QLineEdit, QTextEdit, QPlainTextEdit {{
                background-color: {input_bg};
                color: {text_color};
                border: {input_border};
                border-radius: 3px;
                padding: 4px;
            }}
            QListWidget, QTreeWidget {{
                background-color: {input_bg};
                color: {text_color};
                border: 1px solid #555;
                border-radius: 3px;
            }}
            QListWidget::item:selected {{
                background-color: #007acc;
                color: white;
            }}
            QComboBox {{
                background-color: {btn_bg};
                color: {btn_color};
                border: 1px solid #666;
                border-radius: 3px;
                padding: 3px 8px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {bg_color};
                color: {text_color};
                selection-background-color: #007acc;
            }}
            QGroupBox {{
                color: {text_color};
                border: 1px solid #555;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }}
            QTabWidget::pane {{
                border: 1px solid #555;
                background-color: {bg_color};
            }}
            QTabBar::tab {{
                background-color: {btn_bg};
                color: {btn_color};
                padding: 6px 14px;
                border: 1px solid #555;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {bg_color};
                border-bottom: 2px solid #007acc;
            }}
            QCheckBox {{
                color: {text_color};
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
            QSpinBox {{
                background-color: {input_bg};
                color: {text_color};
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 4px;
            }}
            QScrollBar:vertical {{
                background: {bg_color};
                width: 12px;
            }}
            QScrollBar::handle:vertical {{
                background: #555;
                border-radius: 6px;
                min-height: 30px;
            }}
            QProgressBar {{
                background-color: {input_bg};
                border: 1px solid #555;
                border-radius: 4px;
                text-align: center;
                color: {text_color};
            }}
            QProgressBar::chunk {{
                background-color: #007acc;
                border-radius: 3px;
            }}
            QMenu {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid #555;
            }}
            QMenu::item:selected {{
                background-color: #007acc;
                color: white;
            }}
            QToolTip {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid #555;
                padding: 4px;
            }}
            QFontComboBox {{
                background-color: {input_bg};
                color: {text_color};
                border: 1px solid #555;
            }}
            QScrollArea {{
                background-color: {bg_color};
                border: none;
            }}
            QFrame {{
                color: {text_color};
            }}
            QSlider::groove:horizontal {{
                background: #555;
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: #007acc;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
        """
    else:
        # 浅色主题 — 微调系统默认风格即可
        return f"""
            QDialog {{
                background-color: {bg_color};
                color: {text_color};
            }}
            QLabel {{
                color: {text_color};
                background: transparent;
            }}
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_color};
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px 12px;
            }}
            QPushButton:hover {{
                background-color: #E0E0E0;
            }}
            QPushButton:pressed {{
                background-color: #D0D0D0;
            }}
            QLineEdit, QTextEdit, QPlainTextEdit {{
                background-color: {input_bg};
                color: {text_color};
                border: {input_border};
                border-radius: 3px;
                padding: 4px;
            }}
            QListWidget, QTreeWidget {{
                background-color: {input_bg};
                color: {text_color};
                border: 1px solid #ccc;
                border-radius: 3px;
            }}
            QListWidget::item:selected {{
                background-color: #4a86e8;
                color: white;
            }}
            QGroupBox {{
                color: {text_color};
                border: 1px solid #ccc;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }}
            QTabWidget::pane {{
                border: 1px solid #ccc;
                background-color: {bg_color};
            }}
            QTabBar::tab {{
                background-color: #F0F0F0;
                color: {text_color};
                padding: 6px 14px;
                border: 1px solid #ccc;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {bg_color};
                border-bottom: 2px solid #4a86e8;
            }}
            QCheckBox {{
                color: {text_color};
                spacing: 6px;
            }}
            QComboBox {{
                background-color: white;
                color: {text_color};
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 3px 8px;
            }}
            QSpinBox {{
                background-color: white;
                color: {text_color};
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 2px 4px;
            }}
            QFontComboBox {{
                background-color: white;
                color: {text_color};
                border: 1px solid #ccc;
            }}
            QToolTip {{
                background-color: #FFFFE1;
                color: #000;
                border: 1px solid #767676;
                padding: 4px;
            }}
            QScrollArea {{
                background-color: {bg_color};
                border: none;
            }}
            QScrollBar:vertical {{
                background: #f5f5f5;
                width: 12px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: #ccc;
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: #aaa; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
            QScrollBar:horizontal {{
                background: #f5f5f5;
                height: 12px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: #ccc;
                border-radius: 6px;
                min-width: 30px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: #aaa; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
            QFrame {{
                color: {text_color};
            }}
            QPushButton:disabled {{
                color: #999;
                background-color: #f0f0f0;
            }}
            QSlider::groove:horizontal {{
                background: #ddd;
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: #4a86e8;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
            QProgressBar {{
                background-color: {input_bg};
                border: 1px solid #ccc;
                border-radius: 4px;
                text-align: center;
                color: {text_color};
            }}
            QProgressBar::chunk {{
                background-color: #4a86e8;
                border-radius: 3px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: white;
                color: {text_color};
                selection-background-color: #4a86e8;
            }}
            QMenu {{
                background-color: white;
                color: {text_color};
                border: 1px solid #ccc;
            }}
            QMenu::item:selected {{
                background-color: #4a86e8;
                color: white;
            }}
        """


def _fallback_dialog_style(dark: bool) -> str:
    """默认回退样式（当主题 CSS 加载失败时使用）"""
    if dark:
        return """
            QDialog { background-color: #2b2b2b; color: #e0e0e0; }
            QLabel { color: #e0e0e0; background: transparent; }
            QPushButton { background-color: #555; color: #fff; border: 1px solid #666;
                          border-radius: 4px; padding: 5px 12px; }
            QPushButton:hover { background-color: #666; }
            QLineEdit, QTextEdit { background-color: #3c3c3c; color: #e0e0e0;
                                   border: 1px solid #555; }
        """
    return ''


def apply_dialog_theme(dialog, css_filename: str):
    """
    为指定的 QDialog 应用主题样式。

    Args:
        dialog: QDialog 实例
        css_filename: 当前主题 CSS 文件名
    """
    try:
        stylesheet = generate_dialog_stylesheet(css_filename)
        if stylesheet:
            dialog.setStyleSheet(stylesheet)
    except Exception as e:
        logger.warning(f'应用对话框主题失败: {e}')


def get_current_theme_css(manager) -> str:
    """
    从 manager 获取当前默认主题的 CSS 文件名。

    Args:
        manager: StickyNoteManager 实例

    Returns:
        CSS 文件名（如 'soft_yellow.css'）
    """
    if manager and hasattr(manager, 'get_default_theme_css'):
        return manager.get_default_theme_css()
    return 'soft_yellow.css'

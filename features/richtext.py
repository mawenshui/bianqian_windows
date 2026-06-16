# -*- coding: utf-8 -*-
"""
富文本操作封装模块

RichTextActions 封装所有 QTextCharFormat / QTextBlockFormat 操作，
供 StickyNote 的工具栏按钮调用，避免 note.py 进一步膨胀。
"""

import os
import base64
import logging
from typing import Optional, Dict, Any

from PyQt5.QtWidgets import QTextEdit, QColorDialog, QFileDialog, QInputDialog, QMessageBox
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import (
    QFont, QColor, QTextCharFormat, QTextBlockFormat, QTextCursor,
    QTextListFormat, QTextImageFormat, QImage
)

logger = logging.getLogger(__name__)


class RichTextActions:
    """封装所有 QTextEdit 富文本操作"""

    def __init__(self, text_edit: QTextEdit):
        self.text_edit = text_edit

    # ── 字符格式 ──────────────────────────────────────────

    def toggle_underline(self, enable: bool = None):
        """切换下划线。enable=None 时基于文本格式检测；否则强制设置指定状态。"""
        cursor = self.text_edit.textCursor()
        if enable is None:
            if cursor.hasSelection():
                enable = not cursor.charFormat().fontUnderline()
            else:
                enable = not self.text_edit.currentCharFormat().fontUnderline()
        fmt = QTextCharFormat()
        fmt.setFontUnderline(enable)
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self.text_edit.setCurrentCharFormat(fmt)

    def toggle_strikethrough(self, enable: bool = None):
        """切换删除线。enable=None 时基于文本格式检测；否则强制设置指定状态。"""
        cursor = self.text_edit.textCursor()
        if enable is None:
            if cursor.hasSelection():
                enable = not cursor.charFormat().fontStrikeOut()
            else:
                enable = not self.text_edit.currentCharFormat().fontStrikeOut()
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(enable)
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self.text_edit.setCurrentCharFormat(fmt)

    def toggle_superscript(self):
        """切换上标"""
        cursor = self.text_edit.textCursor()
        current = cursor.charFormat().verticalAlignment() if cursor.hasSelection() else self.text_edit.currentCharFormat().verticalAlignment()
        fmt = QTextCharFormat()
        if current == QTextCharFormat.AlignSuperScript:
            fmt.setVerticalAlignment(QTextCharFormat.AlignNormal)
        else:
            fmt.setVerticalAlignment(QTextCharFormat.AlignSuperScript)
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self.text_edit.setCurrentCharFormat(fmt)

    def toggle_subscript(self):
        """切换下标"""
        cursor = self.text_edit.textCursor()
        current = cursor.charFormat().verticalAlignment() if cursor.hasSelection() else self.text_edit.currentCharFormat().verticalAlignment()
        fmt = QTextCharFormat()
        if current == QTextCharFormat.AlignSubScript:
            fmt.setVerticalAlignment(QTextCharFormat.AlignNormal)
        else:
            fmt.setVerticalAlignment(QTextCharFormat.AlignSubScript)
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self.text_edit.setCurrentCharFormat(fmt)

    def set_highlight_color(self, color: QColor):
        """设置文本高亮（背景色）"""
        cursor = self.text_edit.textCursor()
        fmt = QTextCharFormat()
        fmt.setBackground(color)
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self.text_edit.setCurrentCharFormat(fmt)

    def clear_highlight(self):
        """清除文本高亮"""
        cursor = self.text_edit.textCursor()
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(0, 0, 0, 0))  # 透明背景
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self.text_edit.setCurrentCharFormat(fmt)

    # ── 段落格式 ──────────────────────────────────────────

    def set_alignment(self, alignment: Qt.Alignment):
        """设置段落对齐"""
        cursor = self.text_edit.textCursor()
        block_fmt = QTextBlockFormat()
        block_fmt.setAlignment(alignment)
        cursor.mergeBlockFormat(block_fmt)

    def insert_ordered_list(self):
        """插入有序列表"""
        cursor = self.text_edit.textCursor()
        # 如果已在列表中，则退出列表
        if cursor.currentList():
            cursor.createList(QTextListFormat.ListDecimal)
        else:
            list_format = QTextListFormat()
            list_format.setStyle(QTextListFormat.ListDecimal)
            cursor.createList(list_format)

    def insert_unordered_list(self):
        """插入无序列表"""
        cursor = self.text_edit.textCursor()
        if cursor.currentList():
            cursor.createList(QTextListFormat.ListDisc)
        else:
            list_format = QTextListFormat()
            list_format.setStyle(QTextListFormat.ListDisc)
            cursor.createList(list_format)

    # ── 插入操作 ──────────────────────────────────────────

    def insert_hyperlink(self, url: str, text: str):
        """插入超链接"""
        cursor = self.text_edit.textCursor()
        if not text:
            text = url
        html = f'<a href="{url}" style="color: #007acc; text-decoration: underline;">{text}</a>'
        cursor.insertHtml(html)
        # 插入一个空格以恢复正常输入状态
        cursor.insertText(' ')

    def insert_image_from_file(self, file_path: str, strategy: str = 'base64',
                                notes_dir: str = '', note_id: int = 0) -> bool:
        """
        插入图片到编辑器

        Args:
            file_path: 图片文件路径
            strategy: 'base64' 嵌入 HTML 或 'file_ref' 文件引用
            notes_dir: 便签数据目录（file_ref 模式需要）
            note_id: 便签 ID（file_ref 模式需要）

        Returns:
            True 表示插入成功
        """
        if not os.path.exists(file_path):
            return False

        image = QImage(file_path)
        if image.isNull():
            return False

        cursor = self.text_edit.textCursor()

        if strategy == 'base64':
            # Base64 嵌入
            with open(file_path, 'rb') as f:
                img_data = f.read()
            b64 = base64.b64encode(img_data).decode('ascii')
            ext = os.path.splitext(file_path)[1].lstrip('.').lower()
            if ext == 'jpg':
                ext = 'jpeg'
            mime = f'image/{ext}'
            html = f'<img src="data:{mime};base64,{b64}" />'
            cursor.insertHtml(html)
        else:
            # 文件引用：复制图片到 notes/images/
            if notes_dir:
                images_dir = os.path.join(notes_dir, 'images')
                os.makedirs(images_dir, exist_ok=True)
                dest_name = f'note_{note_id}_{os.path.basename(file_path)}'
                dest_path = os.path.join(images_dir, dest_name)
                import shutil
                shutil.copy2(file_path, dest_path)
                # 注册资源
                url = QUrl.fromLocalFile(dest_path)
                self.text_edit.document().addResource(
                    QTextEdit.ImageResource, url, image
                )
                fmt = QTextImageFormat()
                fmt.setName(dest_path)
                cursor.insertImage(fmt)
            else:
                # 无 notes_dir 时退化为 base64
                return self.insert_image_from_file(file_path, 'base64')

        cursor.insertText(' ')
        return True

    # ── 状态查询 ──────────────────────────────────────────

    def get_current_format_state(self) -> Dict[str, Any]:
        """
        获取当前光标处的格式状态，用于同步按钮 checked 状态。

        Returns:
            dict: 包含 bold, italic, underline, strikethrough,
                  superscript, subscript, alignment, list_type 等键
        """
        fmt = self.text_edit.currentCharFormat()
        block_fmt = self.text_edit.textCursor().blockFormat()

        state = {
            'bold': fmt.fontWeight() == QFont.Bold,
            'italic': fmt.fontItalic(),
            'underline': fmt.fontUnderline(),
            'strikethrough': fmt.fontStrikeOut(),
            'superscript': fmt.verticalAlignment() == QTextCharFormat.AlignSuperScript,
            'subscript': fmt.verticalAlignment() == QTextCharFormat.AlignSubScript,
            'align_left': block_fmt.alignment() == Qt.AlignLeft,
            'align_center': block_fmt.alignment() == Qt.AlignCenter,
            'align_right': block_fmt.alignment() == Qt.AlignRight,
            'in_list': self.text_edit.textCursor().currentList() is not None,
        }

        # 列表类型
        current_list = self.text_edit.textCursor().currentList()
        if current_list:
            list_style = current_list.format().style()
            state['list_ordered'] = list_style == QTextListFormat.ListDecimal
            state['list_unordered'] = list_style == QTextListFormat.ListDisc
        else:
            state['list_ordered'] = False
            state['list_unordered'] = False

        return state

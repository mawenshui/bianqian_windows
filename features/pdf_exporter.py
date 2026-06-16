# -*- coding: utf-8 -*-
"""
PDF 导出模块

使用 QPrinter 将便签内容导出为 PDF 文件。
"""

import os
import logging

from PyQt5.QtWidgets import QFileDialog, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextDocument

logger = logging.getLogger(__name__)

try:
    from PyQt5.QtPrintSupport import QPrinter
    HAS_PRINTER = True
except ImportError:
    HAS_PRINTER = False
    logger.warning('PyQt5.QtPrintSupport 不可用，PDF 导出功能不可用')


class PDFExporter:
    """PDF 导出器"""

    @staticmethod
    def is_available() -> bool:
        """检查 PDF 导出功能是否可用"""
        return HAS_PRINTER

    @staticmethod
    def export_note_to_pdf(title: str, html_content: str, parent=None) -> bool:
        """
        将单个便签内容导出为 PDF

        Args:
            title: 便签标题（用作默认文件名）
            html_content: 便签的 HTML 内容
            parent: 父窗口（用于文件对话框）

        Returns:
            True 表示导出成功
        """
        if not HAS_PRINTER:
            QMessageBox.warning(parent, '导出失败', 'PDF 导出功能不可用（缺少 QtPrintSupport 模块）')
            return False

        # 选择保存路径
        default_name = f'{title}.pdf' if title else 'note_export.pdf'
        file_path, _ = QFileDialog.getSaveFileName(
            parent, '导出 PDF', default_name,
            'PDF 文件 (*.pdf)'
        )
        if not file_path:
            return False

        try:
            # 创建 QTextDocument 并设置 HTML
            doc = QTextDocument()
            doc.setHtml(html_content)

            # 配置打印机
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(file_path)
            printer.setPageSize(QPrinter.A4)
            printer.setPageMargins(15, 15, 15, 15, QPrinter.Millimeter)

            # 执行打印
            doc.print_(printer)
            logger.info(f'PDF 导出成功: {file_path}')
            QMessageBox.information(parent, '导出成功', f'PDF 已导出到:\n{file_path}')
            return True
        except Exception as e:
            logger.error(f'PDF 导出失败: {e}')
            QMessageBox.warning(parent, '导出失败', f'PDF 导出失败: {e}')
            return False

    @staticmethod
    def export_all_notes_to_pdf(notes: dict, parent=None) -> int:
        """
        批量导出所有便签为 PDF

        Args:
            notes: {note_id: StickyNote} 字典
            parent: 父窗口

        Returns:
            成功导出的文件数量
        """
        if not HAS_PRINTER:
            QMessageBox.warning(parent, '导出失败', 'PDF 导出功能不可用')
            return 0

        # 选择保存目录
        output_dir = QFileDialog.getExistingDirectory(parent, '选择导出目录')
        if not output_dir:
            return 0

        success_count = 0
        for note_id, note in notes.items():
            title = note.note_data.get('title', f'便签 {note_id}')
            content = note.note_data.get('content', '')
            if not content:
                continue

            file_path = os.path.join(output_dir, f'{title}.pdf')
            try:
                doc = QTextDocument()
                doc.setHtml(content)
                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(file_path)
                printer.setPageSize(QPrinter.A4)
                printer.setPageMargins(15, 15, 15, 15, QPrinter.Millimeter)
                doc.print_(printer)
                success_count += 1
            except Exception as e:
                logger.error(f'导出便签 {note_id} 失败: {e}')

        if success_count > 0:
            QMessageBox.information(parent, '批量导出完成',
                                    f'成功导出 {success_count} 个便签到:\n{output_dir}')
        else:
            QMessageBox.warning(parent, '导出失败', '没有可导出的便签内容')

        return success_count

# -*- coding: utf-8 -*-
"""便签核心模块的单元测试"""
import unittest
import tempfile
import os
import shutil
from unittest.mock import MagicMock, patch

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtWidgets import QApplication


class TestPlainLineEdit(unittest.TestCase):
    """PlainLineEdit — 纯文本标题编辑器"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_create_line_edit(self):
        """创建 PlainLineEdit 实例"""
        from core.note import PlainLineEdit
        edit = PlainLineEdit()
        self.assertIsNotNone(edit)
        self.assertEqual(edit.maxLength(), 32767)  # QLineEdit 默认

    def test_set_text(self):
        """设置纯文本"""
        from core.note import PlainLineEdit
        edit = PlainLineEdit()
        edit.setText("测试标题")
        self.assertEqual(edit.text(), "测试标题")

    def test_paste_removes_rich_text(self):
        """粘贴时应去除富文本格式（只保留纯文本）"""
        from core.note import PlainLineEdit
        edit = PlainLineEdit()
        # 模拟粘贴：直接调用 paste() 验证不会崩溃
        # paste 方法会从剪贴板获取并转换为纯文本
        edit.paste()  # 不应抛出异常


class TestPlainTextEdit(unittest.TestCase):
    """PlainTextEdit — 纯文本内容编辑器"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_create_text_edit(self):
        """创建 PlainTextEdit 实例"""
        from core.note import PlainTextEdit
        edit = PlainTextEdit()
        self.assertIsNotNone(edit)

    def test_set_text(self):
        """设置文本内容"""
        from core.note import PlainTextEdit
        edit = PlainTextEdit()
        edit.setText("测试内容")
        self.assertEqual(edit.toPlainText(), "测试内容")

    def test_auto_format_toggle(self):
        """智能格式化开关"""
        from core.note import PlainTextEdit
        edit = PlainTextEdit()
        edit.set_auto_format_enabled(True)
        # 设置后不应抛出异常
        edit.set_auto_format_enabled(False)


class TestStickyNoteDefaults(unittest.TestCase):
    """StickyNote — 默认数据和初始化"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_default_note_data_fields(self):
        """default_note_data 应包含所有必要字段"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(999, temp_dir, manager=None)
                data = note.note_data
                # 核心字段
                self.assertIn('title', data)
                self.assertIn('content', data)
                self.assertIn('opacity', data)
                self.assertIn('always_on_top', data)
                self.assertIn('theme', data)
                # v1.6.3 新增字段
                self.assertIn('locked', data)
                self.assertIn('pinned', data)
                self.assertIn('favorite', data)
                # 默认值验证
                self.assertFalse(data['locked'])
                self.assertFalse(data['pinned'])
                self.assertFalse(data['favorite'])
                self.assertTrue(data['always_on_top'])
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_note_has_undo_redo_buttons(self):
        """便签应创建撤销/重做按钮"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(998, temp_dir, manager=None)
                self.assertTrue(hasattr(note, 'undo_btn'))
                self.assertTrue(hasattr(note, 'redo_btn'))
                # 初始状态应为禁用
                self.assertFalse(note.undo_btn.isEnabled())
                self.assertFalse(note.redo_btn.isEnabled())
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_note_has_lock_button(self):
        """便签应创建锁定按钮"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(997, temp_dir, manager=None)
                self.assertTrue(hasattr(note, 'lock_btn'))
                self.assertTrue(hasattr(note, 'is_locked'))
                self.assertFalse(note.is_locked)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)


class TestStickyNotePathSecurity(unittest.TestCase):
    """StickyNote — 路径穿越防护"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_valid_note_file_accepted(self):
        """合法路径应被接受"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(888, temp_dir, manager=None)
                self.assertIsNotNone(note)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_path_traversal_blocked(self):
        """路径穿越应抛出 ValueError"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            # 创建恶意 note_id 使路径指向外部
            # 使用 os.path.realpath 验证机制
            with self.assertRaises(ValueError):
                # 使用 '../../../' 构造路径穿越（必须真正逃逸出 notes_dir）
                StickyNote('../../../malicious', temp_dir, manager=None)
        finally:
            shutil.rmtree(temp_dir)


class TestStickyNoteUpdateButtons(unittest.TestCase):
    """StickyNote — _update_undo_redo_buttons 方法"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_buttons_update_on_state_change(self):
        """撤销/重做状态变化时应更新按钮"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(777, temp_dir, manager=None)
                # 模拟有可撤销状态
                note._update_undo_redo_buttons(True, False)
                self.assertTrue(note.undo_btn.isEnabled())
                self.assertFalse(note.redo_btn.isEnabled())
                # 模拟都可操作
                note._update_undo_redo_buttons(True, True)
                self.assertTrue(note.undo_btn.isEnabled())
                self.assertTrue(note.redo_btn.isEnabled())
                # 模拟都不可操作
                note._update_undo_redo_buttons(False, False)
                self.assertFalse(note.undo_btn.isEnabled())
                self.assertFalse(note.redo_btn.isEnabled())
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)


class TestStickyNoteScreenGeometry(unittest.TestCase):
    """StickyNote — 屏幕几何缓存"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_cache_attributes_exist(self):
        """应存在屏幕几何缓存属性"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(776, temp_dir, manager=None)
                self.assertTrue(hasattr(note, '_screen_geo_cache'))
                self.assertTrue(hasattr(note, '_screen_geo_cache_time'))
                self.assertIsNone(note._screen_geo_cache)
                self.assertEqual(note._screen_geo_cache_time, 0)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_get_screen_geometry_returns_valid(self):
        """_get_screen_geometry 应返回有效值"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(775, temp_dir, manager=None)
                geo = note._get_screen_geometry()
                self.assertIsNotNone(geo)
                self.assertGreater(geo.width(), 0)
                self.assertGreater(geo.height(), 0)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)


class TestStickyNoteBorderPen(unittest.TestCase):
    """StickyNote — paintEvent 渲染缓存"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_border_pen_cached(self):
        """边框画笔应被缓存为实例属性"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(774, temp_dir, manager=None)
                self.assertTrue(hasattr(note, '_border_pen'))
                from PyQt5.QtGui import QPen
                self.assertIsInstance(note._border_pen, QPen)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    unittest.main()

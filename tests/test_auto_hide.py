# -*- coding: utf-8 -*-
"""贴边自动隐藏功能测试"""
import unittest
import tempfile
import os
import shutil
from unittest.mock import MagicMock, patch, PropertyMock

from PyQt5.QtCore import QPoint, QRect, Qt, QEvent
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QApplication


class TestAutoHideSlideOut(unittest.TestCase):
    """贴边隐藏滑出动画 — 目标位置应完全移出屏幕"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def _create_note(self, temp_dir):
        from core.note import StickyNote
        with patch('core.note.get_position_manager') as mp:
            mp.return_value.get_smart_position.return_value = QPoint(200, 200)
            mp.return_value.is_position_valid.return_value = True
            note = StickyNote(800, temp_dir, manager=None)
        return note

    def test_slide_out_left_completely_offscreen(self):
        """左边缘隐藏：便签应完全移出屏幕左侧"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.resize(400, 300)
            note.move(0, 100)
            note.auto_hidden = True
            note.hidden_edge = 'left'
            note._pre_hide_geometry = note.geometry()

            # 模拟屏幕区域
            mock_screen = QRect(0, 0, 1920, 1080)
            with patch.object(note, '_get_screen_geometry', return_value=mock_screen):
                note._slide_out_animation('left')
                # 动画的目标位置
                target = note._slide_anim.endValue()
                w = note.width()
                # 便签右边缘 = target.x() + w，应 < screen.left()
                self.assertLess(target.x() + w, mock_screen.left() + 1,
                                f"左边缘隐藏后便签右边缘 {target.x() + w} 应在屏幕左边缘 {mock_screen.left()} 之外")
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_slide_out_right_completely_offscreen(self):
        """右边缘隐藏：便签应完全移出屏幕右侧"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.resize(400, 300)
            note.move(1520, 100)
            note.auto_hidden = True
            note.hidden_edge = 'right'
            note._pre_hide_geometry = note.geometry()

            mock_screen = QRect(0, 0, 1920, 1080)
            with patch.object(note, '_get_screen_geometry', return_value=mock_screen):
                note._slide_out_animation('right')
                target = note._slide_anim.endValue()
                # 便签左边缘 = target.x()，应 > screen.right()
                self.assertGreater(target.x(), mock_screen.right(),
                                   f"右边缘隐藏后便签左边缘 {target.x()} 应在屏幕右边缘 {mock_screen.right()} 之外")
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_slide_out_top_completely_offscreen(self):
        """上边缘隐藏：便签应完全移出屏幕上侧"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.resize(400, 300)
            note.move(200, 0)
            note.auto_hidden = True
            note.hidden_edge = 'top'
            note._pre_hide_geometry = note.geometry()

            mock_screen = QRect(0, 0, 1920, 1080)
            with patch.object(note, '_get_screen_geometry', return_value=mock_screen):
                note._slide_out_animation('top')
                target = note._slide_anim.endValue()
                h = note.height()
                # 便签下边缘 = target.y() + h，应 < screen.top()
                self.assertLess(target.y() + h, mock_screen.top() + 1,
                                f"上边缘隐藏后便签下边缘 {target.y() + h} 应在屏幕上边缘 {mock_screen.top()} 之外")
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_slide_out_bottom_completely_offscreen(self):
        """下边缘隐藏：便签应完全移出屏幕下侧"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.resize(400, 300)
            note.move(200, 780)
            note.auto_hidden = True
            note.hidden_edge = 'bottom'
            note._pre_hide_geometry = note.geometry()

            mock_screen = QRect(0, 0, 1920, 1080)
            with patch.object(note, '_get_screen_geometry', return_value=mock_screen):
                note._slide_out_animation('bottom')
                target = note._slide_anim.endValue()
                # 便签上边缘 = target.y()，应 > screen.bottom()
                self.assertGreater(target.y(), mock_screen.bottom(),
                                   f"下边缘隐藏后便签上边缘 {target.y()} 应在屏幕下边缘 {mock_screen.bottom()} 之外")
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)


class TestAutoHideMouseGuards(unittest.TestCase):
    """贴边隐藏状态下的鼠标事件防护"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def _create_note(self, temp_dir):
        from core.note import StickyNote
        with patch('core.note.get_position_manager') as mp:
            mp.return_value.get_smart_position.return_value = QPoint(200, 200)
            mp.return_value.is_position_valid.return_value = True
            note = StickyNote(801, temp_dir, manager=None)
        return note

    def test_mouse_move_ignored_when_auto_hidden(self):
        """auto_hidden=True 时 mouseMoveEvent 不应改变光标"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.auto_hidden = True
            note.resize(400, 300)

            # 模拟鼠标在窗口边缘（本应触发缩放光标）
            from PyQt5.QtCore import QEvent as QE
            from PyQt5.QtGui import QMouseEvent
            event = QMouseEvent(QE.MouseMove, QPoint(2, 150), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
            note.mouseMoveEvent(event)

            # 光标应保持为箭头，不应变成缩放光标
            cursor_shape = note.cursor().shape()
            self.assertEqual(cursor_shape, Qt.ArrowCursor,
                             f"auto_hidden 时鼠标应为箭头光标，实际为 {cursor_shape}")
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_mouse_press_ignored_when_auto_hidden(self):
        """auto_hidden=True 时 mousePressEvent 不应启动拖拽"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.auto_hidden = True
            note.resize(400, 300)

            from PyQt5.QtCore import QEvent as QE
            from PyQt5.QtGui import QMouseEvent
            event = QMouseEvent(QE.MouseButtonPress, QPoint(200, 150),
                                Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            note.mousePressEvent(event)

            # 拖拽状态不应被设置
            self.assertFalse(note.dragging,
                             "auto_hidden 时点击不应启动拖拽")
            self.assertFalse(note.resizing,
                             "auto_hidden 时点击不应启动缩放")
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_mouse_events_work_when_not_hidden(self):
        """auto_hidden=False 时鼠标事件正常响应"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.auto_hidden = False
            note.resize(400, 300)

            from PyQt5.QtCore import QEvent as QE
            from PyQt5.QtGui import QMouseEvent
            event = QMouseEvent(QE.MouseButtonPress, QPoint(200, 150),
                                Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            note.mousePressEvent(event)

            # 应启动拖拽状态
            self.assertTrue(note.dragging,
                            "非隐藏状态时点击应启动拖拽")
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)


class TestAutoHideCheckTrigger(unittest.TestCase):
    """贴边隐藏触发条件测试"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def _create_note(self, temp_dir):
        from core.note import StickyNote
        with patch('core.note.get_position_manager') as mp:
            mp.return_value.get_smart_position.return_value = QPoint(200, 200)
            mp.return_value.is_position_valid.return_value = True
            note = StickyNote(802, temp_dir, manager=None)
        return note

    def test_auto_hide_triggers_near_left_edge(self):
        """便签靠近左边缘时触发自动隐藏"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.resize(400, 300)
            note.move(2, 100)  # 距左边缘 2px，小于阈值 3px

            mock_screen = QRect(0, 0, 1920, 1080)
            with patch.object(note, '_get_screen_geometry', return_value=mock_screen):
                note._check_auto_hide()
                self.assertTrue(note.auto_hidden,
                                "便签距左边缘 2px 应触发自动隐藏")
                self.assertEqual(note.hidden_edge, 'left')
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_auto_hide_not_triggered_far_from_edge(self):
        """便签远离边缘时不触发自动隐藏"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.resize(400, 300)
            note.move(500, 400)  # 远离所有边缘

            mock_screen = QRect(0, 0, 1920, 1080)
            with patch.object(note, '_get_screen_geometry', return_value=mock_screen):
                note._check_auto_hide()
                self.assertFalse(note.auto_hidden,
                                 "便签在屏幕中央不应触发自动隐藏")
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_auto_hide_not_triggered_when_already_hidden(self):
        """已处于自动隐藏状态时不重复触发"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.resize(400, 300)
            note.move(0, 100)
            note.auto_hidden = True  # 已经隐藏

            mock_screen = QRect(0, 0, 1920, 1080)
            with patch.object(note, '_get_screen_geometry', return_value=mock_screen):
                # 不应抛出异常或重复创建 hide_tab
                note._check_auto_hide()
                self.assertTrue(note.auto_hidden)
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)


class TestHideTabPositioning(unittest.TestCase):
    """隐藏标签页定位测试"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def _create_note(self, temp_dir):
        from core.note import StickyNote
        with patch('core.note.get_position_manager') as mp:
            mp.return_value.get_smart_position.return_value = QPoint(200, 200)
            mp.return_value.is_position_valid.return_value = True
            note = StickyNote(803, temp_dir, manager=None)
        return note

    def test_hide_tab_at_left_edge(self):
        """左边缘隐藏时标签页应在屏幕左侧"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.resize(400, 300)
            note.move(0, 200)
            note.auto_hidden = True
            note.hidden_edge = 'left'
            note._pre_hide_geometry = note.geometry()
            note._create_hide_tab()

            mock_screen = QRect(0, 0, 1920, 1080)
            with patch.object(note, '_get_screen_geometry', return_value=mock_screen):
                note._position_hide_tab()
                tab_pos = note.hide_tab.pos()
                # 标签页 x 应等于屏幕左边缘
                self.assertEqual(tab_pos.x(), mock_screen.left())
                # 标签页 y 应在便签垂直居中位置附近
                expected_y = 200 + (300 - 28) // 2
                self.assertEqual(tab_pos.y(), expected_y)

            note.hide_tab.deleteLater()
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_hide_tab_at_right_edge(self):
        """右边缘隐藏时标签页应在屏幕右侧"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.resize(400, 300)
            note.move(1520, 200)
            note.auto_hidden = True
            note.hidden_edge = 'right'
            note._pre_hide_geometry = note.geometry()
            note._create_hide_tab()

            mock_screen = QRect(0, 0, 1920, 1080)
            with patch.object(note, '_get_screen_geometry', return_value=mock_screen):
                note._position_hide_tab()
                tab_pos = note.hide_tab.pos()
                # 标签页右边缘应对齐屏幕右边缘
                self.assertEqual(tab_pos.x(), mock_screen.right() - 130)

            note.hide_tab.deleteLater()
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    unittest.main()

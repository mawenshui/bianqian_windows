# -*- coding: utf-8 -*-
"""贴边自动隐藏功能测试"""
import unittest
import tempfile
import os
import shutil
from unittest.mock import MagicMock, patch, PropertyMock

from PyQt5.QtCore import QPoint, QRect, Qt, QEvent
from PyQt5.QtGui import QCursor, QKeyEvent, QMouseEvent
from PyQt5.QtWidgets import QApplication, QLabel


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
                expected_y = 200 + (300 - note.HIDE_TAB_HEIGHT) // 2
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
                self.assertEqual(tab_pos.x(), mock_screen.right() - note.HIDE_TAB_WIDTH)

            note.hide_tab.deleteLater()
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_hide_tab_uses_theme_vector_icon_and_keyboard_restore(self):
        """隐藏把手应使用主题矢量图标，并保留鼠标/键盘恢复入口。"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.set_theme('dark_modern.css')
            note.auto_hidden = True
            note.hidden_edge = 'left'
            note._pre_hide_geometry = note.geometry()
            note._create_hide_tab()

            icon_label = note.hide_tab.findChild(QLabel, 'hideTabIcon')
            title_label = note.hide_tab.findChild(QLabel, 'hideTabTitle')
            self.assertIsNotNone(icon_label)
            self.assertIsNotNone(title_label)
            self.assertIsNotNone(icon_label.pixmap())
            self.assertFalse(icon_label.pixmap().isNull())
            self.assertEqual(icon_label.text(), '')
            self.assertEqual(note.hide_tab.focusPolicy(), Qt.StrongFocus)
            self.assertTrue(note.hide_tab.accessibleName())
            self.assertTrue(icon_label.testAttribute(Qt.WA_TransparentForMouseEvents))
            self.assertTrue(title_label.testAttribute(Qt.WA_TransparentForMouseEvents))
            self.assertIn('QWidget#hideTab:focus', note.hide_tab.styleSheet())
            self.assertIn(
                note._current_theme_styles['surface'].lower(),
                note.hide_tab.styleSheet().lower(),
            )

            # A theme change while hidden refreshes the existing handle.
            note.set_theme('high_contrast.css')
            self.assertIn('#ffff00', note.hide_tab.styleSheet().lower())

            key_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
            with patch.object(note, '_restore_from_auto_hide') as restore:
                self.assertTrue(note.eventFilter(note.hide_tab, key_event))
                restore.assert_called_once_with(hover_triggered=False)

            note.hide_tab.deleteLater()
            note.hide_tab = None
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_arrow_hover_does_not_preview_but_title_hover_does(self):
        """从标题移到箭头应取消预览，移回标题可重新计时。"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.auto_hidden = True
            note.hidden_edge = 'left'
            note._pre_hide_geometry = note.geometry()
            note._create_hide_tab()
            note.hide_tab.show()
            QApplication.processEvents()

            def move_at(pos):
                event = QMouseEvent(QEvent.MouseMove, pos, Qt.NoButton,
                                    Qt.NoButton, Qt.NoModifier)
                note.eventFilter(note.hide_tab, event)

            arrow = note.hide_tab.findChild(QLabel, 'hideTabIcon').geometry().center()
            title = note.hide_tab.findChild(QLabel, 'hideTabTitle').geometry().center()
            move_at(arrow)
            self.assertFalse(note._hover_restore_timer.isActive())
            move_at(title)
            self.assertTrue(note._hover_restore_timer.isActive())
            move_at(arrow)
            self.assertFalse(note._hover_restore_timer.isActive())
            move_at(title)
            note.eventFilter(note.hide_tab, QEvent(QEvent.Leave))
            self.assertFalse(note._hover_restore_timer.isActive())
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_only_left_click_on_arrow_pins_note(self):
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.auto_hidden = True
            note.hidden_edge = 'left'
            note._pre_hide_geometry = note.geometry()
            note._create_hide_tab()
            note.hide_tab.show()
            QApplication.processEvents()
            arrow = note.hide_tab.findChild(QLabel, 'hideTabIcon').geometry().center()
            title = note.hide_tab.findChild(QLabel, 'hideTabTitle').geometry().center()

            def press_at(pos, button):
                event = QMouseEvent(QEvent.MouseButtonPress, pos, button,
                                    button, Qt.NoModifier)
                return note.eventFilter(note.hide_tab, event)

            with patch.object(note, '_restore_from_auto_hide') as restore:
                press_at(title, Qt.LeftButton)
                press_at(arrow, Qt.RightButton)
                restore.assert_not_called()
                self.assertTrue(press_at(arrow, Qt.LeftButton))
                restore.assert_called_once_with(hover_triggered=False)
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_hover_preview_rehides_to_original_edge(self):
        """预览动画结束后保留原边缘，并在鼠标离开时重新收起。"""
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.move(1520, 200)
            note.auto_hidden = True
            note.hidden_edge = 'right'
            note._pre_hide_geometry = note.geometry()
            note._create_hide_tab()
            with patch.object(note, '_get_screen_geometry', return_value=QRect(0, 0, 1920, 1080)):
                note._restore_from_auto_hide(hover_triggered=True)
                note._slide_anim.stop()
                note._on_restore_finished()
                self.assertTrue(note._hover_restored)
                self.assertIsNotNone(note._pre_hide_geometry)
                self.assertEqual(note.hidden_edge, 'right')
                with patch('core.note.QCursor.pos', return_value=QPoint(-1000, -1000)):
                    with patch.object(note, '_slide_out_animation') as slide_out:
                        note._check_and_rehide()
                        slide_out.assert_called_once_with('right')
                self.assertTrue(note.auto_hidden)
                self.assertEqual(note.hidden_edge, 'right')
                self.assertIsNotNone(note.hide_tab)
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_click_restore_clears_preview_state(self):
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.auto_hidden = True
            note.hidden_edge = 'left'
            note._pre_hide_geometry = note.geometry()
            note._create_hide_tab()
            note._restore_from_auto_hide(hover_triggered=False)
            note._slide_anim.stop()
            note._on_restore_finished()
            self.assertFalse(note.auto_hidden)
            self.assertFalse(note._hover_restored)
            self.assertIsNone(note.hidden_edge)
            self.assertIsNone(note._pre_hide_geometry)
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_clicking_preview_note_does_not_pin_it(self):
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note._hover_restored = True
            note._pre_hide_geometry = note.geometry()
            note.hidden_edge = 'left'
            note._schedule_rehide_check()
            event = QMouseEvent(QEvent.MouseButtonPress, QPoint(200, 150),
                                Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            note.mousePressEvent(event)
            self.assertTrue(note._hover_restored)
            self.assertTrue(note._auto_rehide_timer.isActive())
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_legacy_setting_restores_whole_tab_hover_and_click(self):
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.set_hover_preview_enabled(False)
            note.auto_hidden = True
            note.hidden_edge = 'left'
            note._pre_hide_geometry = note.geometry()
            note._create_hide_tab()
            note.hide_tab.show()
            QApplication.processEvents()
            arrow = note.hide_tab.findChild(QLabel, 'hideTabIcon').geometry().center()
            title = note.hide_tab.findChild(QLabel, 'hideTabTitle').geometry().center()
            note._update_hide_tab_hover(arrow)
            self.assertTrue(note._hover_restore_timer.isActive())
            note._hover_restore_timer.stop()
            click = QMouseEvent(QEvent.MouseButtonPress, title, Qt.LeftButton,
                                Qt.LeftButton, Qt.NoModifier)
            with patch.object(note, '_restore_from_auto_hide') as restore:
                self.assertTrue(note.eventFilter(note.hide_tab, click))
                restore.assert_called_once_with(hover_triggered=False)
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_preview_shows_hint_and_arrow_can_pin(self):
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.auto_hidden = True
            note.hidden_edge = 'left'
            note._pre_hide_geometry = note.geometry()
            note._create_hide_tab()
            note._restore_from_auto_hide(hover_triggered=True)
            note._slide_anim.stop()
            self.assertTrue(note.preview_hint.isVisibleTo(note))
            self.assertIn('预览模式', note.preview_hint.text())
            self.assertEqual(note.hide_tab.width(), note.PREVIEW_TAB_WIDTH)
            with patch('core.note.QCursor.pos', return_value=note.hide_tab.geometry().center()):
                note._check_and_rehide()
            self.assertTrue(note._hover_restored)
            arrow = note.hide_tab.findChild(QLabel, 'hideTabIcon').geometry().center()
            click = QMouseEvent(QEvent.MouseButtonPress, arrow, Qt.LeftButton,
                                Qt.LeftButton, Qt.NoModifier)
            self.assertTrue(note.eventFilter(note.hide_tab, click))
            self.assertFalse(note._hover_restored)
            self.assertFalse(note.preview_hint.isVisibleTo(note))
            self.assertIsNone(note.hide_tab)
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_live_setting_toggle_changes_active_preview(self):
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            note.auto_hidden = True
            note.hidden_edge = 'left'
            note._pre_hide_geometry = note.geometry()
            note._create_hide_tab()
            note._restore_from_auto_hide(hover_triggered=True)
            note._slide_anim.stop()
            note.set_hover_preview_enabled(False)
            self.assertTrue(note._hover_restored)
            self.assertIsNone(note.hide_tab)
            self.assertFalse(note.preview_hint.isVisibleTo(note))
            note.set_hover_preview_enabled(True)
            self.assertIsNotNone(note.hide_tab)
            self.assertEqual(note.hide_tab.width(), note.PREVIEW_TAB_WIDTH)
            self.assertTrue(note.preview_hint.isVisibleTo(note))
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_multiple_edge_tabs_do_not_overlap_on_any_side(self):
        """相同位置的便签贴到同一边时，每个箭头都必须可见可点击。"""
        for edge in ('left', 'right', 'top', 'bottom'):
            with self.subTest(edge=edge):
                temp_dir = tempfile.mkdtemp()
                notes = []
                try:
                    for _ in range(3):
                        note = self._create_note(temp_dir)
                        note.resize(400, 300)
                        note.move(200, 200)
                        note.auto_hidden = True
                        note.hidden_edge = edge
                        note._pre_hide_geometry = note.geometry()
                        notes.append(note)
                    screen = QRect(0, 0, 1920, 1080)
                    for note in notes:
                        with patch.object(note, '_get_screen_geometry', return_value=screen):
                            note._create_hide_tab()
                            note.hide_tab.show()
                    QApplication.processEvents()
                    for index, note in enumerate(notes):
                        for other in notes[index + 1:]:
                            self.assertFalse(
                                note.hide_tab.geometry().intersects(other.hide_tab.geometry())
                            )
                finally:
                    for note in notes:
                        note.is_deleted = True
                        note.close()
                    shutil.rmtree(temp_dir)

    def test_event_filter_is_safe_during_note_construction(self):
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._create_note(temp_dir)
            hide_tab = note.hide_tab
            del note.hide_tab
            try:
                note.eventFilter(note, QEvent(QEvent.Enter))
            finally:
                note.hide_tab = hide_tab
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_preview_arrow_reserves_full_width_and_dense_tabs_use_next_row(self):
        temp_dir = tempfile.mkdtemp()
        notes = []
        try:
            screen = QRect(0, 0, 320, 150)
            for _ in range(3):
                note = self._create_note(temp_dir)
                note.resize(240, 240)
                note.move(40, 0)
                note.auto_hidden = True
                note.hidden_edge = 'top'
                note._pre_hide_geometry = note.geometry()
                notes.append(note)
            first = notes[0]
            with patch.object(first, '_get_screen_geometry', return_value=screen):
                first._create_hide_tab()
                first.hide_tab.show()
                first._set_hide_tab_preview_mode(True)
            for note in notes[1:]:
                with patch.object(note, '_get_screen_geometry', return_value=screen):
                    note._create_hide_tab()
                    note.hide_tab.show()
            QApplication.processEvents()
            self.assertGreaterEqual(notes[2].hide_tab.property('edgeLayer'), 1)
            self.assertEqual(notes[0].hide_tab.width(), notes[0].PREVIEW_TAB_WIDTH)
            with patch.object(notes[0], '_get_screen_geometry', return_value=screen):
                notes[0]._set_hide_tab_preview_mode(False)
            for index, note in enumerate(notes):
                for other in notes[index + 1:]:
                    self.assertFalse(
                        note.hide_tab.geometry().intersects(other.hide_tab.geometry())
                    )
        finally:
            for note in notes:
                note.is_deleted = True
                note.close()
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    unittest.main()

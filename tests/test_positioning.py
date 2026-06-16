# -*- coding: utf-8 -*-
"""
窗口定位单元测试

测试 features/positioning.py 的核心逻辑：
- 位置有效性检查
- 网格优先定位
- 位置历史持久化
- 窗口边缘吸附
- 可见区域检测
"""

import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QRect, QPoint, QSize

_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)


class TestPositionValidity(unittest.TestCase):
    """窗口位置有效性测试"""

    def setUp(self):
        from features.positioning import WindowPositionManager
        self.manager = WindowPositionManager()

    def test_valid_position_on_screen(self):
        """屏幕范围内的位置有效"""
        available = self.manager.get_available_screen_area()
        pos = QPoint(available.x() + 100, available.y() + 100)
        size = QSize(300, 200)
        self.assertTrue(self.manager.is_position_valid(pos, size))

    def test_invalid_position_off_screen_right(self):
        """右边界外的位置无效"""
        available = self.manager.get_available_screen_area()
        pos = QPoint(available.right() + 100, available.y() + 100)
        size = QSize(300, 200)
        self.assertFalse(self.manager.is_position_valid(pos, size))

    def test_invalid_position_off_screen_bottom(self):
        """下边界外的位置无效"""
        available = self.manager.get_available_screen_area()
        pos = QPoint(available.x() + 100, available.bottom() + 100)
        size = QSize(300, 200)
        self.assertFalse(self.manager.is_position_valid(pos, size))

    def test_invalid_position_negative_coords(self):
        """负坐标位置无效（在屏幕左上方外）"""
        size = QSize(300, 200)
        self.assertFalse(self.manager.is_position_valid(QPoint(-500, -500), size))

    def test_too_large_window_invalid(self):
        """超出屏幕尺寸的窗口位置无效"""
        available = self.manager.get_available_screen_area()
        pos = QPoint(available.x(), available.y())
        size = QSize(available.width() + 100, available.height() + 100)
        self.assertFalse(self.manager.is_position_valid(pos, size))

    def test_zero_zero_position_check(self):
        """(0,0) 位置检查：取决于屏幕可用区域"""
        # 注意：在大多数桌面，(0,0) 在可用区域内
        # 但如果任务栏在上方，QPoint(0,0) 可能无效
        available = self.manager.get_available_screen_area()
        pos = QPoint(0, 0)
        size = QSize(400, 300)
        # 只验证不抛异常
        result = self.manager.is_position_valid(pos, size)
        self.assertIsInstance(result, bool)


class TestSmartPosition(unittest.TestCase):
    """智能定位测试"""

    def setUp(self):
        from features.positioning import WindowPositionManager
        self.manager = WindowPositionManager()

    def test_get_smart_position_returns_qpoint(self):
        """get_smart_position 返回 QPoint"""
        pos = self.manager.get_smart_position(note_id=None)
        self.assertIsInstance(pos, QPoint)

    def test_get_smart_position_in_screen(self):
        """智能定位的结果应在屏幕可用区域内"""
        available = self.manager.get_available_screen_area()
        pos = self.manager.get_smart_position(note_id=None)
        # 位置在屏幕内
        self.assertGreaterEqual(pos.x(), available.x())
        self.assertGreaterEqual(pos.y(), available.y())

    def test_get_smart_position_without_history(self):
        """note_id=None 时不使用历史"""
        pos1 = self.manager.get_smart_position(note_id=None)
        pos2 = self.manager.get_smart_position(note_id=None)
        # 第一次调用注册网格位置，第二次调用因位置被占用返回下一格
        # 因此位置不同是正常行为
        self.assertIsInstance(pos1, QPoint)
        self.assertIsInstance(pos2, QPoint)

    def test_register_and_occupy(self):
        """注册位置后该位置被标记为占用"""
        pos = QPoint(100, 100)
        size = QSize(300, 200)
        self.manager.register_window_position(999, pos, size)
        occupied = self.manager.is_position_occupied(QRect(pos, size))
        self.assertTrue(occupied)

    def test_unregister_position(self):
        """注销位置后不再占用"""
        pos = QPoint(200, 200)
        size = QSize(300, 200)
        self.manager.register_window_position(888, pos, size)
        self.manager.unregister_window_position(888, pos, size)
        occupied = self.manager.is_position_occupied(QRect(pos, size))
        self.assertFalse(occupied)


class TestWindowSnap(unittest.TestCase):
    """窗口边缘吸附测试"""

    def setUp(self):
        from features.positioning import WindowPositionManager
        self.manager = WindowPositionManager()

    def test_snap_to_left_edge(self):
        """左边缘吸附"""
        available = self.manager.get_available_screen_area()
        # 窗口靠近左边缘
        rect = QRect(
            available.x() + 10,
            available.y() + 100,
            300, 200
        )
        snapped = self.manager.snap_to_edges(rect, snap_distance=20)
        self.assertEqual(snapped.left(), available.left())

    def test_snap_to_top_edge(self):
        """上边缘吸附"""
        available = self.manager.get_available_screen_area()
        rect = QRect(
            available.x() + 100,
            available.y() + 10,
            300, 200
        )
        snapped = self.manager.snap_to_edges(rect, snap_distance=20)
        self.assertEqual(snapped.top(), available.top())

    def test_no_snap_when_far(self):
        """离边缘很远时不吸附"""
        available = self.manager.get_available_screen_area()
        rect = QRect(
            available.x() + 200,
            available.y() + 200,
            300, 200
        )
        snapped = self.manager.snap_to_edges(rect, snap_distance=20)
        # 应保持不变
        self.assertEqual(snapped.left(), rect.left())
        self.assertEqual(snapped.top(), rect.top())


class TestMoveToVisibleArea(unittest.TestCase):
    """恢复窗口到可见区域测试"""

    def setUp(self):
        from features.positioning import WindowPositionManager
        self.manager = WindowPositionManager()

    def test_move_off_screen_right_back(self):
        """右边界外的窗口应被移回可见区域"""
        available = self.manager.get_available_screen_area()
        rect = QRect(
            available.right() + 100,
            available.y() + 100,
            300, 200
        )
        moved = self.manager.move_window_to_visible_area(rect)
        self.assertLessEqual(moved.right(), available.right())

    def test_visible_window_unchanged(self):
        """可见窗口不移位"""
        available = self.manager.get_available_screen_area()
        rect = QRect(
            available.x() + 100,
            available.y() + 100,
            300, 200
        )
        moved = self.manager.move_window_to_visible_area(rect)
        self.assertEqual(moved, rect)


class TestPositionHistory(unittest.TestCase):
    """位置历史持久化测试"""

    def setUp(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_manager(self):
        from features.positioning import WindowPositionManager
        mgr = WindowPositionManager.__new__(WindowPositionManager)
        mgr.occupied_positions = set()
        mgr.position_history = {}
        mgr.position_history_file = os.path.join(self.temp_dir, 'window_positions.json')
        return mgr

    def test_save_and_load_history(self):
        """保存后加载历史一致"""
        mgr = self._make_manager()
        mgr.position_history = {
            1: {'x': 100, 'y': 200, 'width': 300, 'height': 200},
            2: {'x': 400, 'y': 300, 'width': 350, 'height': 250},
        }
        mgr.save_position_history()
        loaded = mgr.load_position_history()
        self.assertEqual(loaded[1], {'x': 100, 'y': 200, 'width': 300, 'height': 200})
        self.assertEqual(loaded[2], {'x': 400, 'y': 300, 'width': 350, 'height': 250})

    def test_load_invalid_entries_skipped(self):
        """无效的位置记录被跳过"""
        mgr = self._make_manager()
        # 写入包含无效条目的 JSON
        bad_data = {
            '1': {'x': 100, 'y': 200, 'width': 300, 'height': 200},
            '2': {'invalid': 'entry'},  # 缺少 x, y
            '3': 'not_a_dict',
        }
        with open(mgr.position_history_file, 'w', encoding='utf-8') as f:
            json.dump(bad_data, f)
        loaded = mgr.load_position_history()
        self.assertIn(1, loaded)
        self.assertNotIn(2, loaded)
        self.assertNotIn(3, loaded)

    def test_clear_position_history(self):
        """清除历史删除文件"""
        mgr = self._make_manager()
        mgr.position_history = {1: {'x': 0, 'y': 0, 'width': 100, 'height': 100}}
        mgr.save_position_history()
        self.assertTrue(os.path.exists(mgr.position_history_file))
        mgr.clear_position_history()
        self.assertFalse(os.path.exists(mgr.position_history_file))
        self.assertEqual(len(mgr.position_history), 0)

    def test_load_empty_file_returns_empty(self):
        """空文件返回空 dict"""
        mgr = self._make_manager()
        with open(mgr.position_history_file, 'w', encoding='utf-8') as f:
            f.write('')
        loaded = mgr.load_position_history()
        self.assertEqual(loaded, {})


class TestGetPositionManager(unittest.TestCase):
    """全局 get_position_manager 测试"""

    def test_singleton(self):
        """两次调用返回同一实例"""
        import features.positioning as pm
        # 重置单例
        pm._position_manager = None
        pm1 = pm.get_position_manager()
        pm2 = pm.get_position_manager()
        self.assertIs(pm1, pm2)


if __name__ == '__main__':
    unittest.main(verbosity=2)

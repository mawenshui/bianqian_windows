# -*- coding: utf-8 -*-
"""撤销/重做功能的单元测试"""
import unittest
from unittest.mock import MagicMock, patch
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication


class TestUndoRedoManager(unittest.TestCase):
    """测试 UndoRedoManager"""

    @classmethod
    def setUpClass(cls):
        """确保 QApplication 存在"""
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self):
        """创建模拟的编辑器和管理器"""
        from features.undo_redo import UndoRedoManager
        self.title_edit = MagicMock()
        self.content_edit = MagicMock()
        self.title_edit.text.return_value = ""
        self.content_edit.toPlainText.return_value = ""
        self.title_edit.cursorPosition.return_value = 0
        self.content_edit.textCursor.return_value.position.return_value = 0
        self.manager = UndoRedoManager(
            self.title_edit, self.content_edit, max_history=50
        )

    def test_initial_state(self):
        """初始状态：不能撤销也不能重做"""
        self.assertFalse(self.manager.can_undo())
        self.assertFalse(self.manager.can_redo())

    def test_get_stack_depth_initial(self):
        """初始栈深度：undo=0, redo=0"""
        ud, rd = self.manager.get_stack_depth()
        self.assertEqual(ud, 0)
        self.assertEqual(rd, 0)

    def test_state_changed_signal_emits_bools(self):
        """state_changed 信号应发射 (can_undo, can_redo)"""
        from features.undo_redo import UndoRedoManager
        from PyQt5.QtWidgets import QLineEdit, QTextEdit
        # 使用真实 QLineEdit/QTextEdit 以触发 textChanged 信号
        title = QLineEdit()
        content = QTextEdit()
        mgr = UndoRedoManager(title, content, max_history=50)
        results = []

        def on_state_changed(can_undo, can_redo):
            results.append((can_undo, can_redo))

        mgr.state_changed.connect(on_state_changed)
        # 修改文本触发信号
        title.setText("新标题")
        # 强制保存触发信号
        mgr.save_current_state(force=True)
        self.assertGreater(len(results), 0)
        if results:
            self.assertIsInstance(results[-1][0], bool)
            self.assertIsInstance(results[-1][1], bool)

    def test_can_undo_after_text_change(self):
        """修改文本后应可撤销"""
        self.title_edit.text.return_value = "新标题"
        self.manager.save_current_state(force=True)
        self.assertTrue(self.manager.can_undo())

    def test_get_history_info(self):
        """获取历史信息应返回字典"""
        info = self.manager.get_history_info()
        self.assertIn('total_states', info)
        self.assertIn('current_index', info)
        self.assertIn('can_undo', info)
        self.assertIn('can_redo', info)

    def test_save_current_state_force(self):
        """强制保存状态应生效"""
        initial_count = len(self.manager.history)
        self.title_edit.text.return_value = "测试"
        self.content_edit.toPlainText.return_value = "内容"
        self.manager.save_current_state(force=True)
        self.assertGreater(len(self.manager.history), initial_count)

    def test_undo_restores_state(self):
        """撤销应恢复到前一个状态"""
        self.title_edit.text.return_value = "状态1"
        self.content_edit.toPlainText.return_value = "内容1"
        self.manager.save_current_state(force=True)
        self.title_edit.text.return_value = "状态2"
        self.content_edit.toPlainText.return_value = "内容2"
        self.manager.save_current_state(force=True)
        self.assertTrue(self.manager.can_undo())
        result = self.manager.undo()
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()

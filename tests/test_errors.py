# -*- coding: utf-8 -*-
"""错误处理模块的单元测试"""
import unittest
from core.errors import (
    StickyNoteError, DataError, FileOperationError,
    PluginError, SearchError, handle_error
)


class TestErrorHierarchy(unittest.TestCase):
    """测试异常层次结构"""

    def test_sticky_note_error_base(self):
        """StickyNoteError 应为基类"""
        self.assertTrue(issubclass(DataError, StickyNoteError))
        self.assertTrue(issubclass(FileOperationError, StickyNoteError))
        self.assertTrue(issubclass(PluginError, StickyNoteError))
        self.assertTrue(issubclass(SearchError, StickyNoteError))

    def test_data_error(self):
        """DataError 应继承自 StickyNoteError"""
        self.assertTrue(issubclass(DataError, StickyNoteError))
        self.assertTrue(issubclass(DataError, Exception))

    def test_file_operation_error(self):
        """FileOperationError 应继承自 StickyNoteError"""
        self.assertTrue(issubclass(FileOperationError, StickyNoteError))

    def test_plugin_error(self):
        """PluginError 应继承自 StickyNoteError"""
        self.assertTrue(issubclass(PluginError, StickyNoteError))

    def test_search_error(self):
        """SearchError 应继承自 StickyNoteError"""
        self.assertTrue(issubclass(SearchError, StickyNoteError))


class TestErrorMessages(unittest.TestCase):
    """测试异常消息"""

    def test_error_with_message(self):
        """异常应携带正确的消息"""
        e = DataError("数据损坏")
        self.assertEqual(str(e), "数据损坏")

    def test_error_with_details(self):
        """异常应支持 original 属性"""
        orig = ValueError("原始错误")
        e = FileOperationError("写入失败", original=orig)
        self.assertEqual(e.original, orig)


class TestHandleError(unittest.TestCase):
    """测试 handle_error 分层处理函数"""

    def test_handle_data_error(self):
        """handle_error 应能处理 DataError"""
        try:
            handle_error(DataError("测试错误"), "test_op")
        except DataError:
            self.fail("handle_error should not raise for DataError")

    def test_handle_unknown_error(self):
        """handle_error 应能处理未知异常"""
        try:
            handle_error(ValueError("未知错误"), "test_op")
        except Exception:
            self.fail("handle_error should handle unknown errors gracefully")


if __name__ == '__main__':
    unittest.main()

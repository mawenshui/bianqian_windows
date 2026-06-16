# -*- coding: utf-8 -*-
"""搜索功能的单元测试"""
import unittest
import tempfile
import os
import json
from unittest.mock import MagicMock, patch


class TestSearchRelevance(unittest.TestCase):
    """测试相关度评分"""

    def setUp(self):
        """创建 SearchDialog 用于测试"""
        from PyQt5.QtWidgets import QApplication
        from features.search import SearchDialog

        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])

        self.manager = MagicMock()
        self.manager.notes = {}
        self.manager.notes_dir = tempfile.mkdtemp()
        self.manager.tag_manager = MagicMock()
        self.manager.tag_manager.get_all_tags.return_value = {}
        self.dialog = SearchDialog(self.manager)

    def test_exact_title_match_highest_score(self):
        """标题精确匹配应得最高分"""
        score = self.dialog._compute_relevance("hello", "hello", "", [])
        self.assertEqual(score, 13)  # 10 (exact title) + 3 (word boundary), 'elif in' not reached

    def test_title_contains_score(self):
        """标题包含应得分"""
        score = self.dialog._compute_relevance("hello", "hello world", "", [])
        self.assertGreaterEqual(score, 8)  # 5 (contains) + 3 (word boundary)

    def test_content_match_lower_score(self):
        """内容匹配应得分较低"""
        score = self.dialog._compute_relevance("hello", "other", "hello world", [])
        self.assertEqual(score, 2)  # only content match

    def test_no_match_zero_score(self):
        """无匹配应为0分"""
        score = self.dialog._compute_relevance("xyz", "abc", "def", [])
        self.assertEqual(score, 0)


class TestSearchIndex(unittest.TestCase):
    """测试搜索索引"""

    def setUp(self):
        """创建 SearchManager 并构建测试数据"""
        from features.search import SearchManager

        self.temp_dir = tempfile.mkdtemp()
        self.manager = MagicMock()
        self.manager.notes = {}
        self.manager.notes_dir = self.temp_dir

        # 创建测试便签文件
        note1 = {"title": "测试便签", "content": "这是测试内容", "tags": []}
        note2 = {"title": "工作笔记", "content": "会议纪要", "tags": ["工作"]}
        with open(os.path.join(self.temp_dir, "note_1.json"), "w", encoding="utf-8") as f:
            json.dump(note1, f, ensure_ascii=False)
        with open(os.path.join(self.temp_dir, "note_2.json"), "w", encoding="utf-8") as f:
            json.dump(note2, f, ensure_ascii=False)

        self.search_mgr = SearchManager(self.manager)

    def test_index_built_on_init(self):
        """初始化时应自动构建索引"""
        self.assertTrue(self.search_mgr._index_built)
        self.assertEqual(len(self.search_mgr._note_index), 2)

    def test_search_uses_index(self):
        """search_notes 应使用索引查找"""
        results = self.search_mgr.search_notes("测试")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], 1)

    def test_refresh_index(self):
        """refresh_index 应重建索引"""
        # 添加新便签文件
        note3 = {"title": "新便签", "content": "新内容", "tags": []}
        with open(os.path.join(self.temp_dir, "note_3.json"), "w", encoding="utf-8") as f:
            json.dump(note3, f, ensure_ascii=False)
        self.search_mgr.refresh_index()
        self.assertEqual(len(self.search_mgr._note_index), 3)


if __name__ == '__main__':
    unittest.main()

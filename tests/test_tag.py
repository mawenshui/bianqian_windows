# -*- coding: utf-8 -*-
"""标签管理模块的单元测试"""
import unittest
import tempfile
import os
import json
from unittest.mock import MagicMock, patch


class TestTagManager(unittest.TestCase):
    """TagManager — 标签的增删改查"""

    def setUp(self):
        """创建 TagManager 实例用于测试"""
        from features.tag import TagManager

        self.temp_dir = tempfile.mkdtemp()
        self.manager = MagicMock()
        self.manager.notes = {}
        self.manager.settings_file = os.path.join(self.temp_dir, 'settings.json')

        self.tag_mgr = TagManager(self.manager)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_with_empty_tags(self):
        """初始化时没有标签文件应为空"""
        self.assertEqual(self.tag_mgr.tags, {})

    def test_add_tag(self):
        """添加新标签"""
        result = self.tag_mgr.add_tag("工作")
        self.assertTrue(result)
        self.assertIn("工作", self.tag_mgr.tags)
        self.assertIsNotNone(self.tag_mgr.tags["工作"])

    def test_add_duplicate_tag_fails(self):
        """不能添加重复标签"""
        self.tag_mgr.add_tag("工作")
        result = self.tag_mgr.add_tag("工作")
        self.assertFalse(result)

    def test_add_empty_tag_fails(self):
        """空名称标签添加失败"""
        result = self.tag_mgr.add_tag("")
        self.assertFalse(result)
        result = self.tag_mgr.add_tag("   ")
        self.assertFalse(result)

    def test_auto_assign_color(self):
        """自动分配颜色"""
        result = self.tag_mgr.add_tag("测试")
        self.assertTrue(result)
        color = self.tag_mgr.tags["测试"]
        self.assertTrue(color.startswith('#'))
        self.assertEqual(len(color), 7)  # #RRGGBB

    def test_remove_tag(self):
        """删除标签"""
        self.tag_mgr.add_tag("待删除")
        self.assertIn("待删除", self.tag_mgr.tags)
        self.tag_mgr.remove_tag("待删除")
        self.assertNotIn("待删除", self.tag_mgr.tags)

    def test_remove_nonexistent_tag(self):
        """删除不存在的标签不应报错"""
        self.tag_mgr.remove_tag("不存在")
        # 不应抛出异常

    def test_rename_tag(self):
        """重命名标签"""
        self.tag_mgr.add_tag("旧名称")
        result = self.tag_mgr.rename_tag("旧名称", "新名称")
        self.assertTrue(result)
        self.assertNotIn("旧名称", self.tag_mgr.tags)
        self.assertIn("新名称", self.tag_mgr.tags)

    def test_rename_to_existing_name_fails(self):
        """重命名为已存在的标签名应失败"""
        self.tag_mgr.add_tag("标签A")
        self.tag_mgr.add_tag("标签B")
        result = self.tag_mgr.rename_tag("标签A", "标签B")
        self.assertFalse(result)

    def test_rename_nonexistent_tag(self):
        """重命名不存在的标签返回 False"""
        result = self.tag_mgr.rename_tag("不存在", "新名称")
        self.assertFalse(result)

    def test_set_tag_color(self):
        """设置标签颜色"""
        self.tag_mgr.add_tag("彩色标签")
        self.tag_mgr.set_tag_color("彩色标签", "#ff0000")
        self.assertEqual(self.tag_mgr.tags["彩色标签"], "#ff0000")

    def test_set_color_nonexistent_tag(self):
        """对不存在的标签设置颜色不应报错"""
        self.tag_mgr.set_tag_color("不存在", "#000000")
        # 不应抛出异常

    def test_get_tag_color(self):
        """获取标签颜色"""
        self.tag_mgr.add_tag("颜色测试")
        color = self.tag_mgr.get_tag_color("颜色测试")
        self.assertTrue(color.startswith('#'))

    def test_get_color_default_for_unknown(self):
        """不存在的标签返回默认颜色"""
        color = self.tag_mgr.get_tag_color("不存在")
        self.assertEqual(color, '#888888')

    def test_get_all_tags_returns_copy(self):
        """get_all_tags 应返回副本"""
        self.tag_mgr.add_tag("标签1")
        tags = self.tag_mgr.get_all_tags()
        tags["新标签"] = "#000000"
        # 原始数据不应被修改
        self.assertNotIn("新标签", self.tag_mgr.tags)

    def test_get_notes_by_tag(self):
        """按标签获取便签"""
        note = MagicMock()
        note.note_data = {"tags": ["工作", "重要"]}
        self.manager.notes = {1: note}

        notes = self.tag_mgr.get_notes_by_tag("工作")
        self.assertEqual(notes, [1])

        notes = self.tag_mgr.get_notes_by_tag("不存在")
        self.assertEqual(notes, [])

    def test_persistence_save_and_load(self):
        """标签持久化：保存后重新加载"""
        from features.tag import TagManager

        self.tag_mgr.add_tag("持久标签")
        color = self.tag_mgr.tags["持久标签"]

        # 重新加载
        new_mgr = TagManager(self.manager)
        self.assertIn("持久标签", new_mgr.tags)
        self.assertEqual(new_mgr.tags["持久标签"], color)


class TestTagColors(unittest.TestCase):
    """标签颜色常量"""

    def test_tag_colors_are_valid(self):
        """所有预设颜色应为有效的 HEX 格式"""
        from features.tag import TAG_COLORS
        for color in TAG_COLORS:
            self.assertTrue(color.startswith('#'))
            self.assertEqual(len(color), 7)


if __name__ == '__main__':
    unittest.main()

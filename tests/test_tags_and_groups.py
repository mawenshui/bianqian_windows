#!/usr/bin/env python3
"""
测试标签和分组功能模块
"""
import sys
import os
import json
import tempfile
import shutil
import unittest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockManager:
    """模拟管理器"""
    def __init__(self, test_dir):
        self.notes_dir = os.path.join(test_dir, 'notes')
        os.makedirs(self.notes_dir, exist_ok=True)


class TestTagManager(unittest.TestCase):
    """测试标签管理器"""
    
    def setUp(self):
        """每个测试前运行"""
        self.test_dir = tempfile.mkdtemp()
        from features.tags import TagManager
        self.TagManager = TagManager
        self.manager = MockManager(self.test_dir)
        self.tag_manager = self.TagManager(self.manager)
    
    def tearDown(self):
        """每个测试后运行"""
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_add_tag(self):
        """测试添加标签"""
        tag = "测试标签"
        result = self.tag_manager.add_tag(tag)
        self.assertEqual(result, tag)
        self.assertIn(tag, self.tag_manager.get_all_tags())
    
    def test_add_existing_tag(self):
        """测试添加已存在的标签"""
        tag = "重复标签"
        self.tag_manager.add_tag(tag)
        tag_info = self.tag_manager.get_tag_info(tag)
        initial_count = tag_info['count'] if tag_info else 0
        
        # 再次添加相同标签
        self.tag_manager.add_tag(tag)
        tag_info = self.tag_manager.get_tag_info(tag)
        self.assertEqual(tag_info['count'], initial_count)
    
    def test_remove_tag(self):
        """测试删除标签"""
        tag = "待删除标签"
        self.tag_manager.add_tag(tag)
        self.assertIn(tag, self.tag_manager.get_all_tags())
        
        self.tag_manager.remove_tag(tag)
        self.assertNotIn(tag, self.tag_manager.get_all_tags())
    
    def test_update_tag_count(self):
        """测试更新标签计数"""
        tag = "计数测试标签"
        self.tag_manager.add_tag(tag)
        
        self.tag_manager.update_tag_count(tag, increment=True)
        tag_info = self.tag_manager.get_tag_info(tag)
        self.assertEqual(tag_info['count'], 1)
        
        self.tag_manager.update_tag_count(tag, increment=True)
        tag_info = self.tag_manager.get_tag_info(tag)
        self.assertEqual(tag_info['count'], 2)
        
        self.tag_manager.update_tag_count(tag, increment=False)
        tag_info = self.tag_manager.get_tag_info(tag)
        self.assertEqual(tag_info['count'], 1)
    
    def test_update_tag_color(self):
        """测试更新标签颜色"""
        tag = "颜色测试标签"
        self.tag_manager.add_tag(tag)
        
        new_color = "#ff0000"
        self.tag_manager.update_tag_color(tag, new_color)
        tag_info = self.tag_manager.get_tag_info(tag)
        self.assertEqual(tag_info['color'], new_color)
    
    def test_get_all_tags(self):
        """测试获取所有标签"""
        tags = ["标签1", "标签2", "标签3"]
        for tag in tags:
            self.tag_manager.add_tag(tag)
        
        all_tags = self.tag_manager.get_all_tags()
        for tag in tags:
            self.assertIn(tag, all_tags)


class TestGroupManager(unittest.TestCase):
    """测试分组管理器"""
    
    def setUp(self):
        """每个测试前运行"""
        self.test_dir = tempfile.mkdtemp()
        from features.groups import GroupManager
        self.GroupManager = GroupManager
        self.manager = MockManager(self.test_dir)
        self.group_manager = self.GroupManager(self.manager)
    
    def tearDown(self):
        """每个测试后运行"""
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_add_group(self):
        """测试添加分组"""
        group = "测试分组"
        result = self.group_manager.add_group(group)
        self.assertEqual(result, group)
        self.assertIn(group, self.group_manager.get_all_groups())
    
    def test_remove_group(self):
        """测试删除分组"""
        group = "待删除分组"
        self.group_manager.add_group(group)
        self.assertIn(group, self.group_manager.get_all_groups())
        
        self.group_manager.remove_group(group)
        self.assertNotIn(group, self.group_manager.get_all_groups())
    
    def test_rename_group(self):
        """测试重命名分组"""
        old_name = "旧分组名"
        new_name = "新分组名"
        self.group_manager.add_group(old_name)
        
        # 添加一个便签到分组
        note_id = 1
        self.group_manager.add_note_to_group(note_id, old_name)
        
        self.group_manager.rename_group(old_name, new_name)
        self.assertNotIn(old_name, self.group_manager.get_all_groups())
        self.assertIn(new_name, self.group_manager.get_all_groups())
        
        # 验证便签仍在分组中
        group_notes = self.group_manager.get_group_notes(new_name)
        self.assertIn(note_id, group_notes)
    
    def test_add_note_to_group(self):
        """测试添加便签到分组"""
        group = "便签分组"
        self.group_manager.add_group(group)
        
        note_id = 1
        self.group_manager.add_note_to_group(note_id, group)
        
        group_notes = self.group_manager.get_group_notes(group)
        self.assertIn(note_id, group_notes)
    
    def test_remove_note_from_group(self):
        """测试从分组移除便签"""
        group = "便签分组"
        self.group_manager.add_group(group)
        
        note_id = 1
        self.group_manager.add_note_to_group(note_id, group)
        
        self.group_manager.remove_note_from_group(note_id)
        group_notes = self.group_manager.get_group_notes(group)
        self.assertNotIn(note_id, group_notes)
    
    def test_get_note_group(self):
        """测试获取便签所在分组"""
        group = "便签分组"
        self.group_manager.add_group(group)
        
        note_id = 1
        self.group_manager.add_note_to_group(note_id, group)
        
        result = self.group_manager.get_note_group(note_id)
        self.assertEqual(result, group)
    
    def test_switch_group(self):
        """测试便签切换分组"""
        group1 = "分组1"
        group2 = "分组2"
        self.group_manager.add_group(group1)
        self.group_manager.add_group(group2)
        
        note_id = 1
        self.group_manager.add_note_to_group(note_id, group1)
        
        # 切换到 group2
        self.group_manager.add_note_to_group(note_id, group2)
        
        # 验证在 group2，不在 group1
        self.assertIn(note_id, self.group_manager.get_group_notes(group2))
        self.assertNotIn(note_id, self.group_manager.get_group_notes(group1))


if __name__ == "__main__":
    unittest.main()

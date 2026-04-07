#!/usr/bin/env python3
"""
运行简化版测试（不依赖 PyQt5）
"""
import sys
import os
import tempfile
import shutil

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("  StickyNote 简化版测试套件")
print("=" * 60)

passed_tests = 0
failed_tests = 0

def run_test(test_name, test_func):
    """运行单个测试"""
    global passed_tests, failed_tests
    print(f"\n测试: {test_name}")
    try:
        test_func()
        print(f"✓ {test_name} 通过")
        passed_tests += 1
    except Exception as e:
        print(f"✗ {test_name} 失败: {e}")
        import traceback
        traceback.print_exc()
        failed_tests += 1

# 创建临时目录
test_dir = tempfile.mkdtemp()

try:
    # 测试 1: utils 模块的函数
    print("\n--- 测试 utils 模块 ---")
    
    # 直接加载 utils 模块，跳过 PyQt5 导入
    utils_code = ""
    utils_path = os.path.join(os.path.dirname(__file__), 'core', 'utils.py')
    with open(utils_path, 'r', encoding='utf-8') as f:
        for line in f:
            # 跳过 PyQt5 相关的导入和类
            if 'from PyQt5' in line or 'import PyQt5' in line:
                continue
            if 'class DebounceTimer' in line:
                break
            utils_code += line
    
    # 添加需要的导入
    utils_code = """
import sys
import os
import json
import traceback
from datetime import datetime
from functools import wraps
""" + utils_code
    
    # 执行 utils 代码
    utils_namespace = {}
    exec(utils_code, utils_namespace)
    
    # 测试 validate_json_data
    def test_validate_json():
        data = {"name": "test", "value": 123}
        required = ["name"]
        result = utils_namespace['validate_json_data'](data, required)
        assert result == True, "应该返回 True"
        
        data = {"name": "test"}
        required = ["name", "missing"]
        result = utils_namespace['validate_json_data'](data, required)
        assert result == False, "应该返回 False"
        
        data = ["not", "a", "dict"]
        result = utils_namespace['validate_json_data'](data)
        assert result == False, "应该返回 False"
    
    run_test("JSON 数据验证", test_validate_json)
    
    # 测试 safe_save_json 和 safe_load_json
    def test_json_save_load():
        test_file = os.path.join(test_dir, "test.json")
        test_data = {"key": "value", "number": 42}
        
        # 保存测试
        result = utils_namespace['safe_save_json'](test_file, test_data)
        assert result == True, "保存应该成功"
        assert os.path.exists(test_file), "文件应该存在"
        
        # 加载测试
        loaded = utils_namespace['safe_load_json'](test_file, default_value={})
        assert loaded == test_data, "加载的数据应该与保存的一致"
        
        # 测试加载不存在的文件
        non_existent = os.path.join(test_dir, "nonexistent.json")
        default = {"default": True}
        loaded = utils_namespace['safe_load_json'](non_existent, default_value=default)
        assert loaded == default, "应该返回默认值"
    
    run_test("JSON 文件保存和加载", test_json_save_load)
    
    # 测试 ensure_directory
    def test_ensure_dir():
        new_dir = os.path.join(test_dir, "new", "nested", "dir")
        result = utils_namespace['ensure_directory'](new_dir)
        assert result == True, "应该返回 True"
        assert os.path.exists(new_dir), "目录应该存在"
    
    run_test("目录创建", test_ensure_dir)
    
    # 测试 get_safe_path
    def test_safe_path():
        base = test_dir
        filename = "../etc/passwd"
        safe = utils_namespace['get_safe_path'](base, filename)
        assert os.path.basename(safe) == "passwd", "文件名应该被正确处理"
        assert safe.startswith(base), "路径应该在基础路径内"
        
        filename = "normal_file.txt"
        safe = utils_namespace['get_safe_path'](base, filename)
        assert safe == os.path.join(base, filename), "正常文件名应该保持不变"
    
    run_test("安全路径获取", test_safe_path)
    
    # 测试 2: 标签功能
    print("\n--- 测试标签功能 ---")
    
    class MockManager:
        def __init__(self, test_dir):
            self.notes_dir = os.path.join(test_dir, 'notes')
            os.makedirs(self.notes_dir, exist_ok=True)
    
    # 直接加载 tags 模块
    tags_code = ""
    tags_path = os.path.join(os.path.dirname(__file__), 'features', 'tags.py')
    with open(tags_path, 'r', encoding='utf-8') as f:
        tags_code = f.read()
    
    tags_namespace = {}
    exec(tags_code, tags_namespace)
    TagManager = tags_namespace['TagManager']
    
    def test_tags():
        manager = MockManager(test_dir)
        tag_manager = TagManager(manager)
        
        # 测试添加标签
        tag = "测试标签"
        result = tag_manager.add_tag(tag)
        assert result == tag, "标签应该被添加"
        assert tag in tag_manager.get_all_tags(), "标签应该在列表中"
        
        # 测试标签计数
        tag_manager.update_tag_count(tag, increment=True)
        tag_info = tag_manager.get_tag_info(tag)
        assert tag_info['count'] == 1, "计数应该为 1"
        
        tag_manager.update_tag_count(tag, increment=True)
        tag_info = tag_manager.get_tag_info(tag)
        assert tag_info['count'] == 2, "计数应该为 2"
        
        tag_manager.update_tag_count(tag, increment=False)
        tag_info = tag_manager.get_tag_info(tag)
        assert tag_info['count'] == 1, "计数应该为 1"
        
        # 测试删除标签
        tag_manager.remove_tag(tag)
        assert tag not in tag_manager.get_all_tags(), "标签应该被删除"
    
    run_test("标签管理器", test_tags)
    
    # 测试 3: 分组功能
    print("\n--- 测试分组功能 ---")
    
    # 直接加载 groups 模块
    groups_code = ""
    groups_path = os.path.join(os.path.dirname(__file__), 'features', 'groups.py')
    with open(groups_path, 'r', encoding='utf-8') as f:
        groups_code = f.read()
    
    groups_namespace = {}
    exec(groups_code, groups_namespace)
    GroupManager = groups_namespace['GroupManager']
    
    def test_groups():
        manager = MockManager(test_dir)
        group_manager = GroupManager(manager)
        
        # 测试添加分组
        group = "测试分组"
        result = group_manager.add_group(group)
        assert result == group, "分组应该被添加"
        assert group in group_manager.get_all_groups(), "分组应该在列表中"
        
        # 测试添加便签到分组
        note_id = 1
        group_manager.add_note_to_group(note_id, group)
        group_notes = group_manager.get_group_notes(group)
        assert note_id in group_notes, "便签应该在分组中"
        
        # 测试获取便签所在分组
        result = group_manager.get_note_group(note_id)
        assert result == group, "应该返回正确的分组"
        
        # 测试从分组移除便签
        group_manager.remove_note_from_group(note_id)
        group_notes = group_manager.get_group_notes(group)
        assert note_id not in group_notes, "便签应该不在分组中"
        
        # 测试删除分组
        group_manager.remove_group(group)
        assert group not in group_manager.get_all_groups(), "分组应该被删除"
    
    run_test("分组管理器", test_groups)
    
finally:
    # 清理临时目录
    shutil.rmtree(test_dir, ignore_errors=True)

# 打印总结
print("\n" + "=" * 60)
print("  测试总结")
print("=" * 60)
print(f"通过测试数: {passed_tests}")
print(f"失败测试数: {failed_tests}")

if failed_tests == 0:
    print("\n🎉 所有测试通过！")
    sys.exit(0)
else:
    print(f"\n❌ 有 {failed_tests} 个测试失败")
    sys.exit(1)

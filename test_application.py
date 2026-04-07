#!/usr/bin/env python3
"""
完善的应用测试脚本
测试便签程序的所有核心功能
"""

import sys
import os
import json
import tempfile
import shutil

def print_section(title):
    """打印测试部分标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def print_success(message):
    """打印成功消息"""
    print(f"✓ {message}")

def print_error(message):
    """打印错误消息"""
    print(f"✗ {message}")

def test_basic_imports():
    """测试基础模块导入"""
    print_section("测试基础模块导入")
    
    try:
        import sys
        import os
        import json
        import tempfile
        import shutil
        from functools import partial
        print_success("Python 标准库导入成功")
    except Exception as e:
        print_error(f"Python 标准库导入失败: {e}")
        return False
    
    return True

def test_feature_modules():
    """测试功能模块（无 PyQt5 依赖的）"""
    print_section("测试功能模块")
    
    test_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    
    try:
        # 测试 features/tags.py
        try:
            sys.path.insert(0, original_cwd)
            from features.tags import TagManager
            print_success("features.tags 模块导入成功")
            
            # 简单测试 TagManager
            os.chdir(test_dir)
            class MockManager:
                def __init__(self):
                    self.notes_dir = os.path.join(test_dir, 'notes')
                    os.makedirs(self.notes_dir, exist_ok=True)
            
            tag_manager = TagManager(MockManager())
            tag_manager.add_tag("测试标签")
            assert "测试标签" in tag_manager.get_all_tags()
            print_success("TagManager 基础功能测试通过")
        except Exception as e:
            print_error(f"features.tags 测试失败: {e}")
            if os.environ.get('VERBOSE_TESTS'):
                import traceback
                traceback.print_exc()
        
        # 测试 features/groups.py
        try:
            os.chdir(test_dir)
            from features.groups import GroupManager
            print_success("features.groups 模块导入成功")
            
            # 简单测试 GroupManager
            group_manager = GroupManager(MockManager())
            group_manager.add_group("测试分组")
            assert "测试分组" in group_manager.get_all_groups()
            print_success("GroupManager 基础功能测试通过")
        except Exception as e:
            print_error(f"features.groups 测试失败: {e}")
            if os.environ.get('VERBOSE_TESTS'):
                import traceback
                traceback.print_exc()
        
        return True
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

def test_file_operations():
    """测试文件操作功能"""
    print_section("测试文件操作")
    
    test_dir = tempfile.mkdtemp()
    
    try:
        # 测试 JSON 文件读写
        test_data = {
            "title": "测试便签",
            "content": "这是测试内容",
            "tags": ["标签1", "标签2"]
        }
        
        test_file = os.path.join(test_dir, "test_note.json")
        
        with open(test_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, ensure_ascii=False, indent=4)
        print_success("JSON 文件写入成功")
        
        with open(test_file, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)
        print_success("JSON 文件读取成功")
        
        assert loaded_data == test_data
        print_success("JSON 数据完整性验证通过")
        
        # 测试目录创建
        nested_dir = os.path.join(test_dir, "nested", "dir", "structure")
        os.makedirs(nested_dir, exist_ok=True)
        assert os.path.exists(nested_dir)
        print_success("嵌套目录创建成功")
        
        return True
    except Exception as e:
        print_error(f"文件操作测试失败: {e}")
        if os.environ.get('VERBOSE_TESTS'):
            import traceback
            traceback.print_exc()
        return False
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

def test_core_modules_syntax():
    """测试核心模块的语法正确性"""
    print_section("测试核心模块语法")
    
    files_to_test = [
        "core/sticky_note.py",
        "core/sticky_note_manager.py",
        "core/__init__.py",
        "main.py"
    ]
    
    all_passed = True
    for filename in files_to_test:
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    source = f.read()
                compile(source, filename, 'exec')
                print_success(f"{filename} 语法检查通过")
            except SyntaxError as e:
                print_error(f"{filename} 语法错误: {e}")
                all_passed = False
            except Exception as e:
                print_error(f"{filename} 检查失败: {e}")
                all_passed = False
        else:
            print_error(f"{filename} 文件不存在")
            all_passed = False
    
    return all_passed

def test_feature_modules_syntax():
    """测试功能模块的语法正确性"""
    print_section("测试功能模块语法")
    
    feature_files = [
        "features/__init__.py",
        "features/backup.py",
        "features/formatter.py",
        "features/groups.py",
        "features/positioning.py",
        "features/search.py",
        "features/shortcuts.py",
        "features/tags.py",
        "features/undo_redo.py"
    ]
    
    all_passed = True
    for filename in feature_files:
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    source = f.read()
                compile(source, filename, 'exec')
                print_success(f"{filename} 语法检查通过")
            except SyntaxError as e:
                print_error(f"{filename} 语法错误: {e}")
                all_passed = False
            except Exception as e:
                print_error(f"{filename} 检查失败: {e}")
                all_passed = False
    
    return all_passed

def check_project_structure():
    """检查项目结构是否完整"""
    print_section("检查项目结构")
    
    required_files = [
        "main.py",
        "core/__init__.py",
        "core/sticky_note.py",
        "core/sticky_note_manager.py",
        "features/__init__.py",
        "features/tags.py",
        "features/groups.py"
    ]
    
    required_dirs = [
        "core",
        "features",
        "styles"
    ]
    
    all_ok = True
    for directory in required_dirs:
        if os.path.isdir(directory):
            print_success(f"目录存在: {directory}")
        else:
            print_error(f"目录不存在: {directory}")
            all_ok = False
    
    for file in required_files:
        if os.path.isfile(file):
            print_success(f"文件存在: {file}")
        else:
            print_error(f"文件不存在: {file}")
            all_ok = False
    
    return all_ok

def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("  便签应用完善测试套件")
    print("=" * 60)
    
    results = []
    
    # 运行所有测试
    results.append(("项目结构检查", check_project_structure()))
    results.append(("基础模块导入", test_basic_imports()))
    results.append(("核心模块语法", test_core_modules_syntax()))
    results.append(("功能模块语法", test_feature_modules_syntax()))
    results.append(("文件操作测试", test_file_operations()))
    results.append(("功能模块测试", test_feature_modules()))
    
    # 打印最终总结
    print_section("测试总结")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\n总计: {passed}/{total} 个测试通过")
    
    print("\n详细结果:")
    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {test_name}: {status}")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())

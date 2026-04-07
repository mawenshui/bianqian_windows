#!/usr/bin/env python3
"""
测试 core.utils 模块
"""
import sys
import os
import json
import tempfile
import shutil
import unittest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 创建虚拟模块来避免 PyQt5 导入错误
class DummyModule:
    pass

# 创建虚拟 PyQt5 模块
sys.modules['PyQt5'] = DummyModule()
sys.modules['PyQt5.QtWidgets'] = DummyModule()
sys.modules['PyQt5.QtCore'] = DummyModule()
sys.modules['PyQt5.QtGui'] = DummyModule()

# 直接导入 utils 模块
utils_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'core', 'utils.py')
with open(utils_path, 'r', encoding='utf-8') as f:
    code = compile(f.read(), utils_path, 'exec')
    namespace = {}
    exec(code, namespace)

validate_json_data = namespace['validate_json_data']
safe_load_json = namespace['safe_load_json']
safe_save_json = namespace['safe_save_json']
ensure_directory = namespace['ensure_directory']
get_safe_path = namespace['get_safe_path']


class TestUtils(unittest.TestCase):
    """测试工具函数"""
    
    def setUp(self):
        """每个测试前运行"""
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """每个测试后运行"""
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_validate_json_data_valid(self):
        """测试有效的 JSON 数据"""
        data = {"name": "test", "value": 123}
        required = ["name"]
        self.assertTrue(validate_json_data(data, required))
    
    def test_validate_json_data_missing_field(self):
        """测试缺少必需字段"""
        data = {"name": "test"}
        required = ["name", "missing"]
        self.assertFalse(validate_json_data(data, required))
    
    def test_validate_json_data_not_dict(self):
        """测试非字典数据"""
        data = ["not", "a", "dict"]
        self.assertFalse(validate_json_data(data))
    
    def test_safe_save_and_load_json(self):
        """测试 JSON 文件的保存和加载"""
        test_file = os.path.join(self.test_dir, "test.json")
        test_data = {"key": "value", "number": 42}
        
        # 保存测试
        result = safe_save_json(test_file, test_data)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(test_file))
        
        # 加载测试
        loaded = safe_load_json(test_file, default_value={})
        self.assertEqual(loaded, test_data)
    
    def test_safe_load_json_nonexistent(self):
        """测试加载不存在的文件"""
        test_file = os.path.join(self.test_dir, "nonexistent.json")
        default = {"default": True}
        loaded = safe_load_json(test_file, default_value=default)
        self.assertEqual(loaded, default)
    
    def test_safe_load_json_invalid(self):
        """测试加载无效的 JSON 文件"""
        test_file = os.path.join(self.test_dir, "invalid.json")
        with open(test_file, 'w') as f:
            f.write("not valid json")
        
        default = {"default": True}
        loaded = safe_load_json(test_file, default_value=default)
        self.assertEqual(loaded, default)
    
    def test_ensure_directory(self):
        """测试目录创建"""
        new_dir = os.path.join(self.test_dir, "new", "nested", "dir")
        result = ensure_directory(new_dir)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(new_dir))
    
    def test_get_safe_path(self):
        """测试安全路径获取"""
        base = self.test_dir
        filename = "../etc/passwd"
        safe = get_safe_path(base, filename)
        self.assertEqual(os.path.basename(safe), "passwd")
        self.assertTrue(safe.startswith(base))
    
    def test_get_safe_path_normal(self):
        """测试正常的文件名"""
        base = self.test_dir
        filename = "normal_file.txt"
        safe = get_safe_path(base, filename)
        self.assertEqual(safe, os.path.join(base, filename))


if __name__ == "__main__":
    unittest.main()

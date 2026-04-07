#!/usr/bin/env python3
"""
运行所有单元测试
"""
import sys
import os
import unittest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_tests():
    """运行所有测试"""
    print("=" * 60)
    print("  StickyNote 单元测试套件")
    print("=" * 60)
    
    # 发现并运行所有测试
    test_loader = unittest.TestLoader()
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    
    if not os.path.exists(test_dir):
        print(f"测试目录不存在: {test_dir}")
        return 1
    
    suite = test_loader.discover(test_dir, pattern='test_*.py')
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 打印总结
    print("\n" + "=" * 60)
    print("  测试总结")
    print("=" * 60)
    print(f"运行测试数: {result.testsRun}")
    print(f"失败数: {len(result.failures)}")
    print(f"错误数: {len(result.errors)}")
    print(f"跳过数: {len(result.skipped)}")
    
    if result.wasSuccessful():
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print("\n❌ 部分测试失败！")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())

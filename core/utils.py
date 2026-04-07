import sys
import os
import json
import traceback
from datetime import datetime
from functools import wraps
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QTimer

def safe_execute(error_message="操作失败", parent=None, show_dialog=True):
    """
    装饰器：安全执行函数，捕获异常并处理
    
    Args:
        error_message: 错误提示信息
        parent: 父窗口对象
        show_dialog: 是否显示错误对话框
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_details = f"{error_message}: {str(e)}\n\n{traceback.format_exc()}"
                log_error(error_details)
                if show_dialog and parent:
                    QMessageBox.warning(parent, "错误", f"{error_message}\n\n{str(e)}")
                return None
        return wrapper
    return decorator

def log_error(message):
    """
    记录错误日志到本地文件
    
    Args:
        message: 错误信息
    """
    try:
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(log_dir, f"error_{timestamp}.log")
        
        log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n{message}\n{'='*60}\n"
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as log_error:
        print(f"无法写入错误日志: {log_error}")

def validate_json_data(data, required_fields=None):
    """
    验证 JSON 数据的完整性
    
    Args:
        data: 待验证的数据
        required_fields: 必需字段列表
    
    Returns:
        bool: 数据是否有效
    """
    if not isinstance(data, dict):
        return False
    
    if required_fields:
        for field in required_fields:
            if field not in data:
                return False
    
    return True

def safe_load_json(file_path, default_value=None):
    """
    安全加载 JSON 文件
    
    Args:
        file_path: JSON 文件路径
        default_value: 默认值
    
    Returns:
        加载的数据或默认值
    """
    if not os.path.exists(file_path):
        return default_value
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        log_error(f"JSON 解析错误: {file_path}")
        return default_value
    except Exception as e:
        log_error(f"加载文件失败 {file_path}: {str(e)}")
        return default_value

def safe_save_json(file_path, data, indent=4):
    """
    安全保存 JSON 文件
    
    Args:
        file_path: JSON 文件路径
        data: 要保存的数据
        indent: 缩进空格数
    
    Returns:
        bool: 是否保存成功
    """
    try:
        # 确保目录存在
        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        
        # 先写入临时文件
        temp_file = file_path + '.tmp'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        
        # 原子性替换原文件
        if os.path.exists(file_path):
            os.replace(temp_file, file_path)
        else:
            os.rename(temp_file, file_path)
        
        return True
    except Exception as e:
        log_error(f"保存文件失败 {file_path}: {str(e)}")
        return False

def ensure_directory(directory):
    """
    确保目录存在，不存在则创建
    
    Args:
        directory: 目录路径
    
    Returns:
        bool: 目录是否存在
    """
    try:
        os.makedirs(directory, exist_ok=True)
        return True
    except Exception as e:
        log_error(f"创建目录失败 {directory}: {str(e)}")
        return False

def get_safe_path(base_path, filename):
    """
    获取安全的文件路径，防止路径遍历攻击
    
    Args:
        base_path: 基础路径
        filename: 文件名
    
    Returns:
        str: 安全的文件路径
    """
    # 移除路径遍历字符
    safe_filename = os.path.basename(filename)
    return os.path.join(base_path, safe_filename)


class DebounceTimer:
    """
    防抖定时器：在指定时间内只执行一次操作
    
    用于避免频繁的重复操作，比如频繁的文件保存
    """
    
    def __init__(self, delay_ms=500):
        """
        初始化防抖定时器
        
        Args:
            delay_ms: 延迟时间（毫秒），默认 500ms
        """
        self.delay_ms = delay_ms
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.callback = None
        self.args = []
        self.kwargs = {}
    
    def schedule(self, callback, *args, **kwargs):
        """
        调度执行回调函数
        
        Args:
            callback: 要执行的回调函数
            *args: 位置参数
            **kwargs: 关键字参数
        """
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        
        if self.timer.isActive():
            self.timer.stop()
        
        self.timer.start(self.delay_ms)
        self.timer.timeout.connect(self._execute_callback)
    
    def _execute_callback(self):
        """执行回调函数"""
        if self.callback:
            try:
                self.callback(*self.args, **self.kwargs)
            except Exception as e:
                log_error(f"防抖执行失败: {str(e)}")
            finally:
                self.callback = None
                self.args = []
                self.kwargs = {}
    
    def cancel(self):
        """取消待执行的操作"""
        if self.timer.isActive():
            self.timer.stop()
        self.callback = None
        self.args = []
        self.kwargs = {}
    
    def force_execute(self):
        """强制执行待执行的操作"""
        if self.callback:
            self.cancel()
            self._execute_callback()

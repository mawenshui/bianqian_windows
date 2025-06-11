# -*- coding: utf-8 -*-
"""
全局快捷键管理模块

提供全局快捷键注册和处理功能
"""

import sys
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QKeySequence

try:
    import win32api
    import win32con
    import win32gui
    from win32gui import RegisterHotKey, UnregisterHotKey
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False
    print("Windows API不可用，全局快捷键功能将被禁用")
    RegisterHotKey = None
    UnregisterHotKey = None


class GlobalShortcutManager(QObject):
    """
    全局快捷键管理器
    
    管理应用程序的全局快捷键
    """
    
    shortcut_activated = pyqtSignal(str)  # 快捷键激活信号
    
    def __init__(self, parent=None):
        """
        初始化全局快捷键管理器
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
        self.shortcuts = {}  # 存储注册的快捷键
        self.hotkey_id = 1  # 热键ID计数器
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_messages)
        
        if WINDOWS_AVAILABLE:
            self.timer.start(50)  # 每50ms检查一次消息
    
    def register_shortcut(self, key_combination, action_name):
        """
        注册全局快捷键
        
        Args:
            key_combination: 快捷键组合 (如 'Ctrl+Shift+N')
            action_name: 动作名称
            
        Returns:
            bool: 注册是否成功
        """
        if not WINDOWS_AVAILABLE:
            print(f"无法注册快捷键 {key_combination}: Windows API 不可用")
            return False
        
        try:
            # 解析快捷键组合
            modifiers, key_code = self.parse_key_combination(key_combination)
            
            if modifiers is None or key_code is None:
                print(f"无法解析快捷键组合: {key_combination}")
                return False
            
            # 注册热键 - 使用NULL窗口句柄
            success = RegisterHotKey(
                None, self.hotkey_id, modifiers, key_code
            )
            
            if success:
                self.shortcuts[self.hotkey_id] = {
                    'combination': key_combination,
                    'action': action_name,
                    'modifiers': modifiers,
                    'key_code': key_code
                }
                print(f"成功注册快捷键: {key_combination} -> {action_name}")
                self.hotkey_id += 1
                return True
            else:
                print(f"注册快捷键失败: {key_combination}")
                return False
                
        except Exception as e:
            print(f"注册快捷键时出错: {e}")
            return False
    
    def unregister_shortcut(self, action_name):
        """
        注销快捷键
        
        Args:
            action_name: 动作名称
            
        Returns:
            bool: 注销是否成功
        """
        if not WINDOWS_AVAILABLE:
            return False
        
        try:
            # 查找要注销的快捷键
            hotkey_id_to_remove = None
            for hotkey_id, shortcut_info in self.shortcuts.items():
                if shortcut_info['action'] == action_name:
                    hotkey_id_to_remove = hotkey_id
                    break
            
            if hotkey_id_to_remove is not None:
                UnregisterHotKey(None, hotkey_id_to_remove)
                del self.shortcuts[hotkey_id_to_remove]
                print(f"成功注销快捷键: {action_name}")
                return True
            else:
                print(f"未找到要注销的快捷键: {action_name}")
                return False
                
        except Exception as e:
            print(f"注销快捷键时出错: {e}")
            return False
    
    def parse_key_combination(self, combination):
        """
        解析快捷键组合
        
        Args:
            combination: 快捷键组合字符串
            
        Returns:
            tuple: (modifiers, key_code) 或 (None, None)
        """
        if not WINDOWS_AVAILABLE:
            return None, None
        
        try:
            parts = combination.split('+')
            modifiers = 0
            key_code = None
            
            for part in parts:
                part = part.strip().lower()
                
                if part == 'ctrl':
                    modifiers |= win32con.MOD_CONTROL
                elif part == 'alt':
                    modifiers |= win32con.MOD_ALT
                elif part == 'shift':
                    modifiers |= win32con.MOD_SHIFT
                elif part == 'win':
                    modifiers |= win32con.MOD_WIN
                else:
                    # 这是主键
                    key_code = self.get_virtual_key_code(part)
            
            return modifiers, key_code
            
        except Exception as e:
            print(f"解析快捷键组合时出错: {e}")
            return None, None
    
    def get_virtual_key_code(self, key):
        """
        获取虚拟键码
        
        Args:
            key: 键名
            
        Returns:
            int: 虚拟键码
        """
        key_map = {
            'a': ord('A'), 'b': ord('B'), 'c': ord('C'), 'd': ord('D'),
            'e': ord('E'), 'f': ord('F'), 'g': ord('G'), 'h': ord('H'),
            'i': ord('I'), 'j': ord('J'), 'k': ord('K'), 'l': ord('L'),
            'm': ord('M'), 'n': ord('N'), 'o': ord('O'), 'p': ord('P'),
            'q': ord('Q'), 'r': ord('R'), 's': ord('S'), 't': ord('T'),
            'u': ord('U'), 'v': ord('V'), 'w': ord('W'), 'x': ord('X'),
            'y': ord('Y'), 'z': ord('Z'),
            '0': ord('0'), '1': ord('1'), '2': ord('2'), '3': ord('3'),
            '4': ord('4'), '5': ord('5'), '6': ord('6'), '7': ord('7'),
            '8': ord('8'), '9': ord('9'),
            'f1': win32con.VK_F1, 'f2': win32con.VK_F2, 'f3': win32con.VK_F3,
            'f4': win32con.VK_F4, 'f5': win32con.VK_F5, 'f6': win32con.VK_F6,
            'f7': win32con.VK_F7, 'f8': win32con.VK_F8, 'f9': win32con.VK_F9,
            'f10': win32con.VK_F10, 'f11': win32con.VK_F11, 'f12': win32con.VK_F12,
            'space': win32con.VK_SPACE, 'enter': win32con.VK_RETURN,
            'escape': win32con.VK_ESCAPE, 'tab': win32con.VK_TAB,
            'backspace': win32con.VK_BACK, 'delete': win32con.VK_DELETE,
            'insert': win32con.VK_INSERT, 'home': win32con.VK_HOME,
            'end': win32con.VK_END, 'pageup': win32con.VK_PRIOR,
            'pagedown': win32con.VK_NEXT, 'up': win32con.VK_UP,
            'down': win32con.VK_DOWN, 'left': win32con.VK_LEFT,
            'right': win32con.VK_RIGHT
        }
        
        return key_map.get(key.lower())
    
    def check_messages(self):
        """
        检查Windows消息队列中的热键消息
        """
        if not WINDOWS_AVAILABLE:
            return
        
        try:
            # 这里应该检查WM_HOTKEY消息
            # 由于PyQt5的限制，我们使用一个简化的实现
            pass
        except Exception as e:
            print(f"检查消息时出错: {e}")
    
    def cleanup(self):
        """
        清理所有注册的快捷键
        """
        if not WINDOWS_AVAILABLE:
            return
        
        try:
            for hotkey_id in list(self.shortcuts.keys()):
                UnregisterHotKey(None, hotkey_id)
            
            self.shortcuts.clear()
            print("已清理所有全局快捷键")
            
        except Exception as e:
            print(f"清理快捷键时出错: {e}")


class LocalShortcutManager(QObject):
    """
    本地快捷键管理器
    
    管理应用程序内的快捷键（当应用程序有焦点时）
    """
    
    shortcut_activated = pyqtSignal(str)  # 快捷键激活信号
    
    def __init__(self, parent=None):
        """
        初始化本地快捷键管理器
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
        self.shortcuts = {}  # 存储快捷键映射
    
    def register_shortcut(self, key_combination, action_name):
        """
        注册本地快捷键
        
        Args:
            key_combination: 快捷键组合
            action_name: 动作名称
            
        Returns:
            bool: 注册是否成功
        """
        try:
            key_sequence = QKeySequence(key_combination)
            if not key_sequence.isEmpty():
                self.shortcuts[key_sequence.toString()] = action_name
                print(f"成功注册本地快捷键: {key_combination} -> {action_name}")
                return True
            else:
                print(f"无效的快捷键组合: {key_combination}")
                return False
        except Exception as e:
            print(f"注册本地快捷键时出错: {e}")
            return False
    
    def unregister_shortcut(self, action_name):
        """
        注销本地快捷键
        
        Args:
            action_name: 动作名称
            
        Returns:
            bool: 注销是否成功
        """
        try:
            key_to_remove = None
            for key, action in self.shortcuts.items():
                if action == action_name:
                    key_to_remove = key
                    break
            
            if key_to_remove:
                del self.shortcuts[key_to_remove]
                print(f"成功注销本地快捷键: {action_name}")
                return True
            else:
                print(f"未找到要注销的本地快捷键: {action_name}")
                return False
        except Exception as e:
            print(f"注销本地快捷键时出错: {e}")
            return False
    
    def handle_key_event(self, event):
        """
        处理键盘事件
        
        Args:
            event: 键盘事件
            
        Returns:
            bool: 是否处理了该事件
        """
        try:
            # 构建按键序列
            key = event.key()
            modifiers = event.modifiers()
            
            key_sequence = QKeySequence(key | int(modifiers))
            key_string = key_sequence.toString()
            
            if key_string in self.shortcuts:
                action_name = self.shortcuts[key_string]
                self.shortcut_activated.emit(action_name)
                return True
            
            return False
        except Exception as e:
            print(f"处理键盘事件时出错: {e}")
            return False
    
    def get_registered_shortcuts(self):
        """
        获取已注册的快捷键列表
        
        Returns:
            dict: 快捷键映射字典
        """
        return self.shortcuts.copy()


class ShortcutManager(QObject):
    """
    快捷键管理器
    
    统一管理全局和本地快捷键
    """
    
    shortcut_activated = pyqtSignal(str)  # 快捷键激活信号
    
    def __init__(self, parent=None):
        """
        初始化快捷键管理器
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
        self.global_manager = GlobalShortcutManager(self)
        self.local_manager = LocalShortcutManager(self)
        
        # 连接信号
        self.global_manager.shortcut_activated.connect(self.shortcut_activated)
        self.local_manager.shortcut_activated.connect(self.shortcut_activated)
    
    def register_global_shortcut(self, key_combination, action_name):
        """
        注册全局快捷键
        
        Args:
            key_combination: 快捷键组合
            action_name: 动作名称
            
        Returns:
            bool: 注册是否成功
        """
        return self.global_manager.register_shortcut(key_combination, action_name)
    
    def register_local_shortcut(self, key_combination, action_name):
        """
        注册本地快捷键
        
        Args:
            key_combination: 快捷键组合
            action_name: 动作名称
            
        Returns:
            bool: 注册是否成功
        """
        return self.local_manager.register_shortcut(key_combination, action_name)
    
    def unregister_shortcut(self, action_name):
        """
        注销快捷键（全局和本地）
        
        Args:
            action_name: 动作名称
        """
        self.global_manager.unregister_shortcut(action_name)
        self.local_manager.unregister_shortcut(action_name)
    
    def handle_key_event(self, event):
        """
        处理键盘事件（用于本地快捷键）
        
        Args:
            event: 键盘事件
            
        Returns:
            bool: 是否处理了该事件
        """
        return self.local_manager.handle_key_event(event)
    
    def cleanup(self):
        """
        清理所有快捷键
        """
        self.global_manager.cleanup()
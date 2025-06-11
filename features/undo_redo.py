# -*- coding: utf-8 -*-
"""
撤销重做功能模块

为便签编辑器提供撤销和重做功能
"""

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QTextEdit, QLineEdit
from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import Qt
import time


class UndoRedoState:
    """
    撤销重做状态类
    
    存储编辑器的状态信息
    """
    
    def __init__(self, title_text, content_text, title_cursor_pos, content_cursor_pos, timestamp=None):
        """
        初始化状态
        
        Args:
            title_text: 标题文本
            content_text: 内容文本
            title_cursor_pos: 标题光标位置
            content_cursor_pos: 内容光标位置
            timestamp: 时间戳
        """
        self.title_text = title_text
        self.content_text = content_text
        self.title_cursor_pos = title_cursor_pos
        self.content_cursor_pos = content_cursor_pos
        self.timestamp = timestamp or time.time()


class UndoRedoManager(QObject):
    """
    撤销重做管理器
    
    管理编辑器的撤销重做操作
    """
    
    state_changed = pyqtSignal()  # 状态变化信号
    
    def __init__(self, title_edit, content_edit, max_history=50):
        """
        初始化撤销重做管理器
        
        Args:
            title_edit: 标题编辑器
            content_edit: 内容编辑器
            max_history: 最大历史记录数量
        """
        super().__init__()
        self.title_edit = title_edit
        self.content_edit = content_edit
        self.max_history = max_history
        
        self.history = []
        self.current_index = -1
        self.last_save_time = 0
        self.save_interval = 1.0  # 保存间隔（秒）
        
        # 连接信号
        self.title_edit.textChanged.connect(self.on_text_changed)
        self.content_edit.textChanged.connect(self.on_text_changed)
        
        # 保存初始状态
        self.save_current_state()
    
    def save_current_state(self, force=False):
        """
        保存当前状态到历史记录
        
        Args:
            force: 是否强制保存
        """
        current_time = time.time()
        
        # 检查是否需要保存（避免频繁保存）
        if not force and (current_time - self.last_save_time) < self.save_interval:
            return
        
        # 获取当前状态
        title_text = self.title_edit.text()
        content_text = self.content_edit.toPlainText()
        title_cursor_pos = self.title_edit.cursorPosition()
        content_cursor_pos = self.content_edit.textCursor().position()
        
        # 检查是否与最后一个状态相同
        if self.history and self.current_index >= 0:
            last_state = self.history[self.current_index]
            if (last_state.title_text == title_text and 
                last_state.content_text == content_text):
                return
        
        # 创建新状态
        new_state = UndoRedoState(
            title_text, content_text, 
            title_cursor_pos, content_cursor_pos,
            current_time
        )
        
        # 如果当前不在历史末尾，删除后续历史
        if self.current_index < len(self.history) - 1:
            self.history = self.history[:self.current_index + 1]
        
        # 添加新状态
        self.history.append(new_state)
        
        # 限制历史记录长度
        if len(self.history) > self.max_history:
            self.history.pop(0)
        else:
            self.current_index += 1
        
        self.last_save_time = current_time
        self.state_changed.emit()
    
    def undo(self):
        """
        撤销操作
        
        Returns:
            bool: 是否成功撤销
        """
        if not self.can_undo():
            return False
        
        # 在撤销前保存当前状态（如果是最新的）
        if self.current_index == len(self.history) - 1:
            self.save_current_state(force=True)
            if self.current_index < len(self.history) - 1:
                self.current_index += 1
        
        # 移动到前一个状态
        self.current_index -= 1
        self.restore_state(self.history[self.current_index])
        self.state_changed.emit()
        return True
    
    def redo(self):
        """
        重做操作
        
        Returns:
            bool: 是否成功重做
        """
        if not self.can_redo():
            return False
        
        # 移动到下一个状态
        self.current_index += 1
        self.restore_state(self.history[self.current_index])
        self.state_changed.emit()
        return True
    
    def restore_state(self, state):
        """
        恢复到指定状态
        
        Args:
            state: 要恢复的状态
        """
        # 临时断开信号连接，避免触发保存
        self.title_edit.textChanged.disconnect(self.on_text_changed)
        self.content_edit.textChanged.disconnect(self.on_text_changed)
        
        try:
            # 恢复文本
            self.title_edit.setText(state.title_text)
            self.content_edit.setPlainText(state.content_text)
            
            # 恢复光标位置
            self.title_edit.setCursorPosition(state.title_cursor_pos)
            
            cursor = self.content_edit.textCursor()
            cursor.setPosition(min(state.content_cursor_pos, len(state.content_text)))
            self.content_edit.setTextCursor(cursor)
            
        finally:
            # 重新连接信号
            self.title_edit.textChanged.connect(self.on_text_changed)
            self.content_edit.textChanged.connect(self.on_text_changed)
    
    def can_undo(self):
        """
        检查是否可以撤销
        
        Returns:
            bool: 是否可以撤销
        """
        return self.current_index > 0
    
    def can_redo(self):
        """
        检查是否可以重做
        
        Returns:
            bool: 是否可以重做
        """
        return self.current_index < len(self.history) - 1
    
    def on_text_changed(self):
        """
        处理文本变化事件
        """
        # 延迟保存状态，避免频繁操作
        self.save_current_state()
    
    def clear_history(self):
        """
        清空历史记录
        """
        self.history.clear()
        self.current_index = -1
        self.save_current_state()
    
    def get_history_info(self):
        """
        获取历史记录信息
        
        Returns:
            dict: 历史记录信息
        """
        return {
            'total_states': len(self.history),
            'current_index': self.current_index,
            'can_undo': self.can_undo(),
            'can_redo': self.can_redo()
        }


class UndoRedoTextEdit(QTextEdit):
    """
    支持撤销重做的文本编辑器
    
    扩展QTextEdit，添加自定义撤销重做功能
    """
    
    def __init__(self, parent=None):
        """
        初始化文本编辑器
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self.undo_redo_manager = None
    
    def set_undo_redo_manager(self, manager):
        """
        设置撤销重做管理器
        
        Args:
            manager: 撤销重做管理器
        """
        self.undo_redo_manager = manager
    
    def keyPressEvent(self, event):
        """
        处理键盘事件
        
        Args:
            event: 键盘事件
        """
        # 处理撤销重做快捷键
        if self.undo_redo_manager:
            if event.matches(QKeySequence.Undo):
                if self.undo_redo_manager.undo():
                    return
            elif event.matches(QKeySequence.Redo):
                if self.undo_redo_manager.redo():
                    return
        
        # 调用父类方法处理其他按键
        super().keyPressEvent(event)


class UndoRedoLineEdit(QLineEdit):
    """
    支持撤销重做的单行编辑器
    
    扩展QLineEdit，添加自定义撤销重做功能
    """
    
    def __init__(self, parent=None):
        """
        初始化单行编辑器
        
        Args:
            parent: 父窗口
        """
        super().__init__(parent)
        self.undo_redo_manager = None
    
    def set_undo_redo_manager(self, manager):
        """
        设置撤销重做管理器
        
        Args:
            manager: 撤销重做管理器
        """
        self.undo_redo_manager = manager
    
    def keyPressEvent(self, event):
        """
        处理键盘事件
        
        Args:
            event: 键盘事件
        """
        # 处理撤销重做快捷键
        if self.undo_redo_manager:
            if event.matches(QKeySequence.Undo):
                if self.undo_redo_manager.undo():
                    return
            elif event.matches(QKeySequence.Redo):
                if self.undo_redo_manager.redo():
                    return
        
        # 调用父类方法处理其他按键
        super().keyPressEvent(event)
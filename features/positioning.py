# -*- coding: utf-8 -*-
"""
智能窗口定位功能模块

提供智能的窗口定位和排列功能
"""

import os
import json
from PyQt5.QtWidgets import QApplication, QDesktopWidget
from PyQt5.QtCore import QRect, QPoint, QSize
from PyQt5.QtGui import QScreen


class WindowPositionManager:
    """
    窗口位置管理器
    
    管理便签窗口的智能定位和排列
    """
    
    def __init__(self):
        """
        初始化窗口位置管理器
        """
        self.app = QApplication.instance()
        self.desktop = QDesktopWidget()
        
        # 窗口间距
        self.window_margin = 20
        
        # 默认窗口大小
        self.default_window_size = QSize(300, 200)
        
        # 已占用的位置
        self.occupied_positions = set()
        
        # 位置历史文件
        self.position_history_file = os.path.join(os.getcwd(), 'window_positions.json')
        
        # 加载位置历史
        self.position_history = self.load_position_history()
    
    def get_smart_position(self, note_id=None, window_size=None):
        """
        获取智能窗口位置
        
        Args:
            note_id: 便签ID
            window_size: 窗口大小
            
        Returns:
            QPoint: 窗口位置
        """
        if window_size is None:
            window_size = self.default_window_size
        
        # 如果有历史位置，优先使用
        if note_id and note_id in self.position_history:
            history_pos = self.position_history[note_id]
            pos = QPoint(history_pos['x'], history_pos['y'])
            
            # 检查位置是否仍然有效
            if self.is_position_valid(pos, window_size):
                return pos
        
        # 获取可用的屏幕区域
        available_rect = self.get_available_screen_area()
        
        # 尝试找到最佳位置
        best_position = self.find_best_position(available_rect, window_size)
        
        return best_position
    
    def get_available_screen_area(self):
        """
        获取可用的屏幕区域（排除任务栏等）
        
        Returns:
            QRect: 可用屏幕区域
        """
        # 获取主屏幕
        primary_screen = self.app.primaryScreen()
        
        # 获取可用几何区域（排除任务栏）
        available_geometry = primary_screen.availableGeometry()
        
        return available_geometry
    
    def find_best_position(self, available_rect, window_size):
        """
        在可用区域内找到最佳窗口位置
        
        Args:
            available_rect: 可用屏幕区域
            window_size: 窗口大小
            
        Returns:
            QPoint: 最佳位置
        """
        # 计算网格大小
        grid_width = window_size.width() + self.window_margin
        grid_height = window_size.height() + self.window_margin
        
        # 计算可以放置的行列数
        cols = max(1, (available_rect.width() - self.window_margin) // grid_width)
        rows = max(1, (available_rect.height() - self.window_margin) // grid_height)
        
        # 尝试按优先级顺序放置窗口
        positions_to_try = self.get_position_priority_order(available_rect, grid_width, grid_height, cols, rows)
        
        for pos in positions_to_try:
            window_rect = QRect(pos, window_size)
            
            # 检查位置是否可用
            if (self.is_position_valid(pos, window_size) and 
                not self.is_position_occupied(window_rect)):
                
                # 标记位置为已占用
                self.occupied_positions.add((pos.x(), pos.y(), window_size.width(), window_size.height()))
                return pos
        
        # 如果没有找到合适位置，使用默认位置（屏幕中心偏移）
        center_x = available_rect.x() + (available_rect.width() - window_size.width()) // 2
        center_y = available_rect.y() + (available_rect.height() - window_size.height()) // 2
        
        # 添加随机偏移避免重叠
        offset = len(self.occupied_positions) * 30
        return QPoint(center_x + offset, center_y + offset)
    
    def get_position_priority_order(self, available_rect, grid_width, grid_height, cols, rows):
        """
        获取位置优先级顺序
        
        Args:
            available_rect: 可用屏幕区域
            grid_width: 网格宽度
            grid_height: 网格高度
            cols: 列数
            rows: 行数
            
        Returns:
            list: 按优先级排序的位置列表
        """
        positions = []
        
        # 策略1: 从左上角开始，按列优先
        for col in range(cols):
            for row in range(rows):
                x = available_rect.x() + self.window_margin + col * grid_width
                y = available_rect.y() + self.window_margin + row * grid_height
                positions.append(QPoint(x, y))
        
        return positions
    
    def is_position_valid(self, position, window_size):
        """
        检查位置是否有效（在屏幕范围内）
        
        Args:
            position: 窗口位置
            window_size: 窗口大小
            
        Returns:
            bool: 位置是否有效
        """
        window_rect = QRect(position, window_size)
        available_rect = self.get_available_screen_area()
        
        # 检查窗口是否完全在可用区域内
        return available_rect.contains(window_rect)
    
    def is_position_occupied(self, window_rect):
        """
        检查位置是否被占用
        
        Args:
            window_rect: 窗口矩形
            
        Returns:
            bool: 位置是否被占用
        """
        for occupied in self.occupied_positions:
            occupied_rect = QRect(occupied[0], occupied[1], occupied[2], occupied[3])
            
            # 检查是否有重叠
            if window_rect.intersects(occupied_rect):
                return True
        
        return False
    
    def register_window_position(self, note_id, position, size):
        """
        注册窗口位置
        
        Args:
            note_id: 便签ID
            position: 窗口位置
            size: 窗口大小
        """
        # 添加到已占用位置
        self.occupied_positions.add((position.x(), position.y(), size.width(), size.height()))
        
        # 保存到历史记录
        if note_id:
            self.position_history[note_id] = {
                'x': position.x(),
                'y': position.y(),
                'width': size.width(),
                'height': size.height()
            }
            self.save_position_history()
    
    def unregister_window_position(self, note_id, position, size):
        """
        注销窗口位置
        
        Args:
            note_id: 便签ID
            position: 窗口位置
            size: 窗口大小
        """
        # 从已占用位置移除
        occupied_tuple = (position.x(), position.y(), size.width(), size.height())
        self.occupied_positions.discard(occupied_tuple)
    
    def update_window_position(self, note_id, old_position, old_size, new_position, new_size):
        """
        更新窗口位置
        
        Args:
            note_id: 便签ID
            old_position: 旧位置
            old_size: 旧大小
            new_position: 新位置
            new_size: 新大小
        """
        # 移除旧位置
        self.unregister_window_position(note_id, old_position, old_size)
        
        # 注册新位置
        self.register_window_position(note_id, new_position, new_size)
    
    def get_cascade_position(self, base_position, index):
        """
        获取层叠位置
        
        Args:
            base_position: 基础位置
            index: 索引
            
        Returns:
            QPoint: 层叠位置
        """
        offset = index * 30  # 每个窗口偏移30像素
        return QPoint(base_position.x() + offset, base_position.y() + offset)
    
    def arrange_windows_grid(self, window_list, cols=None):
        """
        网格排列窗口
        
        Args:
            window_list: 窗口列表
            cols: 列数，如果为None则自动计算
        """
        if not window_list:
            return
        
        available_rect = self.get_available_screen_area()
        
        # 自动计算列数
        if cols is None:
            cols = max(1, int((available_rect.width() / (self.default_window_size.width() + self.window_margin)) ** 0.5))
        
        grid_width = self.default_window_size.width() + self.window_margin
        grid_height = self.default_window_size.height() + self.window_margin
        
        for i, window in enumerate(window_list):
            row = i // cols
            col = i % cols
            
            x = available_rect.x() + self.window_margin + col * grid_width
            y = available_rect.y() + self.window_margin + row * grid_height
            
            # 确保窗口在屏幕范围内
            if x + self.default_window_size.width() <= available_rect.right():
                if y + self.default_window_size.height() <= available_rect.bottom():
                    window.move(x, y)
    
    def arrange_windows_cascade(self, window_list):
        """
        层叠排列窗口
        
        Args:
            window_list: 窗口列表
        """
        if not window_list:
            return
        
        available_rect = self.get_available_screen_area()
        
        # 起始位置
        start_x = available_rect.x() + self.window_margin
        start_y = available_rect.y() + self.window_margin
        
        for i, window in enumerate(window_list):
            pos = self.get_cascade_position(QPoint(start_x, start_y), i)
            
            # 确保窗口在屏幕范围内
            if (pos.x() + self.default_window_size.width() <= available_rect.right() and
                pos.y() + self.default_window_size.height() <= available_rect.bottom()):
                window.move(pos)
            else:
                # 如果超出屏幕，重新开始
                window.move(start_x, start_y)
    
    def snap_to_edges(self, window_rect, snap_distance=20):
        """
        窗口边缘吸附
        
        Args:
            window_rect: 窗口矩形
            snap_distance: 吸附距离
            
        Returns:
            QRect: 调整后的窗口矩形
        """
        available_rect = self.get_available_screen_area()
        
        new_rect = QRect(window_rect)
        
        # 左边缘吸附
        if abs(new_rect.left() - available_rect.left()) <= snap_distance:
            new_rect.moveLeft(available_rect.left())
        
        # 右边缘吸附
        if abs(new_rect.right() - available_rect.right()) <= snap_distance:
            new_rect.moveRight(available_rect.right())
        
        # 上边缘吸附
        if abs(new_rect.top() - available_rect.top()) <= snap_distance:
            new_rect.moveTop(available_rect.top())
        
        # 下边缘吸附
        if abs(new_rect.bottom() - available_rect.bottom()) <= snap_distance:
            new_rect.moveBottom(available_rect.bottom())
        
        return new_rect
    
    def get_next_available_position(self, window_size=None):
        """
        获取下一个可用位置
        
        Args:
            window_size: 窗口大小
            
        Returns:
            QPoint: 下一个可用位置
        """
        if window_size is None:
            window_size = self.default_window_size
        
        return self.get_smart_position(window_size=window_size)
    
    def load_position_history(self):
        """
        加载位置历史
        
        Returns:
            dict: 位置历史数据
        """
        if os.path.exists(self.position_history_file):
            try:
                with open(self.position_history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载位置历史时出错: {e}")
        
        return {}
    
    def save_position_history(self):
        """
        保存位置历史
        """
        try:
            with open(self.position_history_file, 'w', encoding='utf-8') as f:
                json.dump(self.position_history, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存位置历史时出错: {e}")
    
    def clear_position_history(self):
        """
        清除位置历史
        """
        self.position_history.clear()
        self.occupied_positions.clear()
        
        if os.path.exists(self.position_history_file):
            try:
                os.remove(self.position_history_file)
            except Exception as e:
                print(f"删除位置历史文件时出错: {e}")
    
    def get_screen_info(self):
        """
        获取屏幕信息
        
        Returns:
            dict: 屏幕信息
        """
        primary_screen = self.app.primaryScreen()
        geometry = primary_screen.geometry()
        available_geometry = primary_screen.availableGeometry()
        
        return {
            'total_width': geometry.width(),
            'total_height': geometry.height(),
            'available_width': available_geometry.width(),
            'available_height': available_geometry.height(),
            'available_x': available_geometry.x(),
            'available_y': available_geometry.y(),
            'dpi': primary_screen.logicalDotsPerInch()
        }
    
    def is_window_visible(self, window_rect):
        """
        检查窗口是否在可见区域内
        
        Args:
            window_rect: 窗口矩形
            
        Returns:
            bool: 窗口是否可见
        """
        available_rect = self.get_available_screen_area()
        
        # 检查窗口是否至少有一部分在可见区域内
        return window_rect.intersects(available_rect)
    
    def move_window_to_visible_area(self, window_rect):
        """
        将窗口移动到可见区域
        
        Args:
            window_rect: 窗口矩形
            
        Returns:
            QRect: 调整后的窗口矩形
        """
        available_rect = self.get_available_screen_area()
        new_rect = QRect(window_rect)
        
        # 如果窗口超出右边界
        if new_rect.right() > available_rect.right():
            new_rect.moveRight(available_rect.right())
        
        # 如果窗口超出左边界
        if new_rect.left() < available_rect.left():
            new_rect.moveLeft(available_rect.left())
        
        # 如果窗口超出下边界
        if new_rect.bottom() > available_rect.bottom():
            new_rect.moveBottom(available_rect.bottom())
        
        # 如果窗口超出上边界
        if new_rect.top() < available_rect.top():
            new_rect.moveTop(available_rect.top())
        
        return new_rect


# 全局位置管理器实例
_position_manager = None


def get_position_manager():
    """
    获取全局位置管理器实例
    
    Returns:
        WindowPositionManager: 位置管理器实例
    """
    global _position_manager
    if _position_manager is None:
        _position_manager = WindowPositionManager()
    return _position_manager
# -*- coding: utf-8 -*-
"""
性能优化模块

提供：
- AsyncFileWorker: 通用异步文件读写工作线程
- NoteDataCache: 便签数据 LRU 缓存
- LazyLoader: 延迟加载包装器
"""

import json
import os
import logging
import threading
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional

from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


# ==================== 6.1 异步文件 I/O ====================

class AsyncFileWorker(QThread):
    """
    通用异步 JSON 文件读写工作线程。

    用于将非关键的同步文件操作移至后台线程，避免阻塞 UI。
    """

    read_completed = pyqtSignal(str, dict)   # (file_path, data)
    read_failed = pyqtSignal(str, str)       # (file_path, error)
    write_completed = pyqtSignal(str)        # (file_path)
    write_failed = pyqtSignal(str, str)      # (file_path, error)

    def __init__(self, operation: str, file_path: str, data: dict = None):
        """
        Args:
            operation: 'read' 或 'write'
            file_path: 目标文件路径
            data: 写入时的数据字典
        """
        super().__init__()
        self.operation = operation
        self.file_path = file_path
        self.data = data

    def run(self):
        try:
            if self.operation == 'read':
                if os.path.exists(self.file_path):
                    with open(self.file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self.read_completed.emit(self.file_path, data)
                else:
                    self.read_failed.emit(self.file_path, '文件不存在')

            elif self.operation == 'write':
                os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
                tmp_path = self.file_path + '.tmp'
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=4)
                if os.path.exists(self.file_path):
                    os.replace(tmp_path, self.file_path)
                else:
                    os.rename(tmp_path, self.file_path)
                self.write_completed.emit(self.file_path)

        except Exception as e:
            logger.error(f"[AsyncFileWorker] {self.operation} 失败: {self.file_path} - {e}")
            if self.operation == 'read':
                self.read_failed.emit(self.file_path, str(e))
            else:
                self.write_failed.emit(self.file_path, str(e))


def async_write_json(file_path: str, data: dict, parent=None) -> AsyncFileWorker:
    """便捷函数：异步写入 JSON 文件"""
    worker = AsyncFileWorker('write', file_path, data)
    if parent:
        worker.setParent(parent)
    worker.start()
    return worker


def async_read_json(file_path: str, parent=None) -> AsyncFileWorker:
    """便捷函数：异步读取 JSON 文件"""
    worker = AsyncFileWorker('read', file_path)
    if parent:
        worker.setParent(parent)
    worker.start()
    return worker


# ==================== 6.2 便签数据 LRU 缓存 ====================

class NoteDataCache:
    """
    便签数据 LRU 缓存。

    缓存最近访问的便签 JSON 数据，避免搜索时重复读取磁盘文件。
    线程安全（使用锁保护）。
    """

    def __init__(self, max_size: int = 100):
        """
        Args:
            max_size: 最大缓存条目数
        """
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, note_id: int) -> Optional[dict]:
        """获取缓存的便签数据（LRU 提升）"""
        with self._lock:
            if note_id in self._cache:
                self._hits += 1
                # 移到末尾（最近使用）
                self._cache.move_to_end(note_id)
                return self._cache[note_id]
            self._misses += 1
            return None

    def put(self, note_id: int, data: dict) -> None:
        """存入或更新缓存"""
        with self._lock:
            if note_id in self._cache:
                self._cache.move_to_end(note_id)
                self._cache[note_id] = data
            else:
                if len(self._cache) >= self._max_size:
                    # 淘汰最久未使用的
                    self._cache.popitem(last=False)
                self._cache[note_id] = data

    def invalidate(self, note_id: int) -> None:
        """使指定便签缓存失效（删除/更新时调用）"""
        with self._lock:
            self._cache.pop(note_id, None)

    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    @property
    def hit_rate(self) -> float:
        with self._lock:
            total = self._hits + self._misses
            return self._hits / total if total > 0 else 0.0

    def stats(self) -> dict:
        with self._lock:
            return {
                'size': len(self._cache),
                'max_size': self._max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': self.hit_rate,
            }


# 全局缓存单例
_note_cache: Optional[NoteDataCache] = None


def get_note_cache() -> NoteDataCache:
    """获取全局便签数据缓存单例"""
    global _note_cache
    if _note_cache is None:
        _note_cache = NoteDataCache(max_size=100)
    return _note_cache


# ==================== 6.3 延迟加载 ====================

class LazyLoader:
    """
    延迟加载包装器。

    将模块或对象的初始化推迟到首次访问时，
    用于减少启动时间。
    """

    def __init__(self, factory: Callable[[], Any]):
        """
        Args:
            factory: 无参函数，调用时执行真正的初始化
        """
        self._factory = factory
        self._instance = None
        self._lock = threading.Lock()

    @property
    def instance(self) -> Any:
        """获取实例（首次访问时初始化）"""
        if self._instance is None:
            with self._lock:
                if self._instance is None:  # 双重检查锁
                    logger.debug(f"[LazyLoader] 延迟初始化: {self._factory.__name__}")
                    self._instance = self._factory()
        return self._instance

    def reset(self) -> None:
        """重置（下次访问时重新初始化）"""
        with self._lock:
            self._instance = None

    def is_loaded(self) -> bool:
        return self._instance is not None


def lazy_import(module_path: str, class_name: str) -> LazyLoader:
    """
    延迟导入模块中的类。

    Args:
        module_path: 模块路径（如 'features.search'）
        class_name: 类名（如 'SearchManager'）

    Returns:
        LazyLoader 实例
    """
    def _factory():
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return cls
    return LazyLoader(_factory)

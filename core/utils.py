import os
import json
from functools import lru_cache

class LazyLoader:
    """
    延迟加载管理器
    """
    def __init__(self):
        self._loaded_modules = {}
    
    def load_module(self, module_name):
        """
        延迟加载模块
        
        Args:
            module_name: 模块名称
            
        Returns:
            加载的模块
        """
        if module_name not in self._loaded_modules:
            if module_name == 'search':
                from features.search import SearchManager
                self._loaded_modules[module_name] = SearchManager
            elif module_name == 'backup':
                from features.backup import BackupManager
                self._loaded_modules[module_name] = BackupManager
            elif module_name == 'positioning':
                from features.positioning import get_position_manager
                self._loaded_modules[module_name] = get_position_manager
            elif module_name == 'reminder':
                from features.reminder import ReminderManager
                self._loaded_modules[module_name] = ReminderManager
            elif module_name == 'tags':
                from features.tags import TagManager
                self._loaded_modules[module_name] = TagManager
            # 其他模块...
        
        return self._loaded_modules[module_name]

class NoteCache:
    """
    便签缓存管理器
    """
    def __init__(self, max_size=50):
        self.cache = {}
        self.access_order = []
        self.max_size = max_size
    
    def get_note(self, note_id, notes_dir):
        """
        获取便签，使用LRU缓存策略
        
        Args:
            note_id: 便签ID
            notes_dir: 便签存储目录
            
        Returns:
            便签数据
        """
        if note_id in self.cache:
            # 更新访问顺序
            self.access_order.remove(note_id)
            self.access_order.append(note_id)
            return self.cache[note_id]
        
        # 加载便签
        note_data = self.load_note_from_disk(note_id, notes_dir)
        self.cache[note_id] = note_data
        self.access_order.append(note_id)
        
        # 清理缓存
        if len(self.cache) > self.max_size:
            oldest_id = self.access_order.pop(0)
            del self.cache[oldest_id]
        
        return note_data
    
    def load_note_from_disk(self, note_id, notes_dir):
        """
        从磁盘加载便签
        
        Args:
            note_id: 便签ID
            notes_dir: 便签存储目录
            
        Returns:
            便签数据
        """
        note_file = os.path.join(notes_dir, f'note_{note_id}.json')
        if os.path.exists(note_file):
            try:
                with open(note_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        
        # 默认便签数据
        return {
            'title': f'便签 {note_id}',
            'content': '',
            'plain_content': '',
            'opacity': 0.9,
            'always_on_top': True,
            'geometry': None,
            'theme': "soft_yellow.css",
            'title_font_size': 12,
            'content_font_size': 12,
            'auto_format_enabled': True,
            'font_color': '#000000'
        }
    
    def update_note(self, note_id, note_data):
        """
        更新缓存中的便签数据
        
        Args:
            note_id: 便签ID
            note_data: 便签数据
        """
        if note_id in self.cache:
            # 更新访问顺序
            self.access_order.remove(note_id)
            self.access_order.append(note_id)
        else:
            # 添加新便签到缓存
            self.access_order.append(note_id)
            
            # 清理缓存
            if len(self.cache) > self.max_size:
                oldest_id = self.access_order.pop(0)
                del self.cache[oldest_id]
        
        self.cache[note_id] = note_data
    
    def remove_note(self, note_id):
        """
        从缓存中移除便签
        
        Args:
            note_id: 便签ID
        """
        if note_id in self.cache:
            del self.cache[note_id]
            if note_id in self.access_order:
                self.access_order.remove(note_id)

@lru_cache(maxsize=32)
def get_cached_setting(settings_file, key, default=None):
    """
    缓存设置值，避免重复读取文件
    
    Args:
        settings_file: 设置文件路径
        key: 设置键
        default: 默认值
        
    Returns:
        设置值
    """
    if os.path.exists(settings_file):
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                return settings.get(key, default)
        except Exception:
            pass
    return default

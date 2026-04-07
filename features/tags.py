import json
import os

class TagManager:
    def __init__(self, manager):
        self.manager = manager
        self.tags_file = os.path.join(os.getcwd(), 'tags.json')
        self.tags_file = os.path.abspath(self.tags_file)
        self.tags = self.load_tags()
    
    def load_tags(self):
        """加载标签数据"""
        if os.path.exists(self.tags_file):
            try:
                with open(self.tags_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载标签文件出错: {e}")
                return {}
        else:
            return {}
    
    def save_tags(self):
        """保存标签数据"""
        try:
            with open(self.tags_file, 'w', encoding='utf-8') as f:
                json.dump(self.tags, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存标签文件出错: {e}")
    
    def add_tag(self, tag_name):
        """添加标签"""
        if tag_name not in self.tags:
            self.tags[tag_name] = {
                'count': 0,
                'color': '#3498db'  # 默认标签颜色
            }
            self.save_tags()
        return tag_name
    
    def remove_tag(self, tag_name):
        """删除标签"""
        if tag_name in self.tags:
            del self.tags[tag_name]
            self.save_tags()
    
    def update_tag_count(self, tag_name, increment=True):
        """更新标签使用次数"""
        if tag_name in self.tags:
            if increment:
                self.tags[tag_name]['count'] += 1
            else:
                self.tags[tag_name]['count'] = max(0, self.tags[tag_name]['count'] - 1)
            self.save_tags()
    
    def get_all_tags(self):
        """获取所有标签"""
        return list(self.tags.keys())
    
    def get_tag_info(self, tag_name):
        """获取标签信息"""
        return self.tags.get(tag_name, None)
    
    def update_tag_color(self, tag_name, color):
        """更新标签颜色"""
        if tag_name in self.tags:
            self.tags[tag_name]['color'] = color
            self.save_tags()
    
    def get_tags_for_note(self, note_id):
        """获取便签的标签"""
        note_file = os.path.join(self.manager.notes_dir, f'note_{note_id}.json')
        if os.path.exists(note_file):
            try:
                with open(note_file, 'r', encoding='utf-8') as f:
                    note_data = json.load(f)
                    return note_data.get('tags', [])
            except Exception as e:
                print(f"加载便签文件出错: {e}")
                return []
        else:
            return []
    
    def add_tag_to_note(self, note_id, tag_name):
        """为便签添加标签"""
        note_file = os.path.join(self.manager.notes_dir, f'note_{note_id}.json')
        if os.path.exists(note_file):
            try:
                with open(note_file, 'r', encoding='utf-8') as f:
                    note_data = json.load(f)
                
                if 'tags' not in note_data:
                    note_data['tags'] = []
                
                if tag_name not in note_data['tags']:
                    note_data['tags'].append(tag_name)
                    self.add_tag(tag_name)  # 确保标签存在
                    self.update_tag_count(tag_name, increment=True)
                
                with open(note_file, 'w', encoding='utf-8') as f:
                    json.dump(note_data, f, ensure_ascii=False, indent=4)
                
                return True
            except Exception as e:
                print(f"添加标签到便签出错: {e}")
                return False
        else:
            return False
    
    def remove_tag_from_note(self, note_id, tag_name):
        """从便签移除标签"""
        note_file = os.path.join(self.manager.notes_dir, f'note_{note_id}.json')
        if os.path.exists(note_file):
            try:
                with open(note_file, 'r', encoding='utf-8') as f:
                    note_data = json.load(f)
                
                if 'tags' in note_data and tag_name in note_data['tags']:
                    note_data['tags'].remove(tag_name)
                    self.update_tag_count(tag_name, increment=False)
                
                with open(note_file, 'w', encoding='utf-8') as f:
                    json.dump(note_data, f, ensure_ascii=False, indent=4)
                
                return True
            except Exception as e:
                print(f"从便签移除标签出错: {e}")
                return False
        else:
            return False
    
    def search_notes_by_tag(self, tag_name):
        """根据标签搜索便签"""
        matching_notes = []
        for filename in os.listdir(self.manager.notes_dir):
            if filename.startswith('note_') and filename.endswith('.json'):
                try:
                    note_id_str = filename.split('_')[1].split('.')[0]
                    note_id = int(note_id_str)
                    note_tags = self.get_tags_for_note(note_id)
                    if tag_name in note_tags:
                        matching_notes.append(note_id)
                except Exception as e:
                    print(f"搜索便签时出错: {e}")
        return matching_notes
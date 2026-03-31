import json
import os

class GroupManager:
    def __init__(self, manager):
        self.manager = manager
        self.groups_file = os.path.join(os.getcwd(), 'groups.json')
        self.groups_file = os.path.abspath(self.groups_file)
        self.groups = self.load_groups()
    
    def load_groups(self):
        """加载分组数据"""
        if os.path.exists(self.groups_file):
            try:
                with open(self.groups_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载分组文件出错: {e}")
                return {}
        else:
            return {}
    
    def save_groups(self):
        """保存分组数据"""
        try:
            with open(self.groups_file, 'w', encoding='utf-8') as f:
                json.dump(self.groups, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存分组文件出错: {e}")
    
    def add_group(self, group_name):
        """添加分组"""
        if group_name not in self.groups:
            self.groups[group_name] = {
                'note_ids': []
            }
            self.save_groups()
        return group_name
    
    def remove_group(self, group_name):
        """删除分组"""
        if group_name in self.groups:
            # 将分组中的便签移除分组属性
            for note_id in self.groups[group_name]['note_ids']:
                self.remove_note_from_group(note_id)
            del self.groups[group_name]
            self.save_groups()
    
    def rename_group(self, old_name, new_name):
        """重命名分组"""
        if old_name in self.groups and new_name not in self.groups:
            self.groups[new_name] = self.groups[old_name]
            del self.groups[old_name]
            # 更新便签中的分组名称
            for note_id in self.groups[new_name]['note_ids']:
                note_file = os.path.join(self.manager.notes_dir, f'note_{note_id}.json')
                if os.path.exists(note_file):
                    try:
                        with open(note_file, 'r', encoding='utf-8') as f:
                            note_data = json.load(f)
                        note_data['group'] = new_name
                        with open(note_file, 'w', encoding='utf-8') as f:
                            json.dump(note_data, f, ensure_ascii=False, indent=4)
                    except Exception as e:
                        print(f"更新便签分组名称出错: {e}")
            self.save_groups()
    
    def get_all_groups(self):
        """获取所有分组"""
        return list(self.groups.keys())
    
    def get_group_notes(self, group_name):
        """获取分组中的便签"""
        if group_name in self.groups:
            return self.groups[group_name]['note_ids']
        return []
    
    def add_note_to_group(self, note_id, group_name):
        """将便签添加到分组"""
        # 先从原分组中移除
        self.remove_note_from_group(note_id)
        
        # 添加到新分组
        if group_name in self.groups:
            if note_id not in self.groups[group_name]['note_ids']:
                self.groups[group_name]['note_ids'].append(note_id)
                self.save_groups()
        else:
            # 如果分组不存在，创建分组
            self.add_group(group_name)
            self.groups[group_name]['note_ids'].append(note_id)
            self.save_groups()
        
        # 更新便签的分组属性
        note_file = os.path.join(self.manager.notes_dir, f'note_{note_id}.json')
        if os.path.exists(note_file):
            try:
                with open(note_file, 'r', encoding='utf-8') as f:
                    note_data = json.load(f)
                note_data['group'] = group_name
                with open(note_file, 'w', encoding='utf-8') as f:
                    json.dump(note_data, f, ensure_ascii=False, indent=4)
                return True
            except Exception as e:
                print(f"添加便签到分组出错: {e}")
                return False
        else:
            return False
    
    def remove_note_from_group(self, note_id):
        """从分组中移除便签"""
        # 查找便签所在的分组
        for group_name, group_data in self.groups.items():
            if note_id in group_data['note_ids']:
                group_data['note_ids'].remove(note_id)
                self.save_groups()
                break
        
        # 更新便签的分组属性
        note_file = os.path.join(self.manager.notes_dir, f'note_{note_id}.json')
        if os.path.exists(note_file):
            try:
                with open(note_file, 'r', encoding='utf-8') as f:
                    note_data = json.load(f)
                if 'group' in note_data:
                    del note_data['group']
                with open(note_file, 'w', encoding='utf-8') as f:
                    json.dump(note_data, f, ensure_ascii=False, indent=4)
                return True
            except Exception as e:
                print(f"从分组移除便签出错: {e}")
                return False
        else:
            return False
    
    def get_note_group(self, note_id):
        """获取便签所在的分组"""
        note_file = os.path.join(self.manager.notes_dir, f'note_{note_id}.json')
        if os.path.exists(note_file):
            try:
                with open(note_file, 'r', encoding='utf-8') as f:
                    note_data = json.load(f)
                    return note_data.get('group', None)
            except Exception as e:
                print(f"加载便签文件出错: {e}")
                return None
        else:
            return None
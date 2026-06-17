# -*- coding: utf-8 -*-
"""
字数统计插件

统计当前便签的字符数、词数和行数。
"""

from features.plugin_system.base import PluginBase


class WordCountPlugin(PluginBase):
    """字数统计插件"""

    name = '字数统计'
    version = '1.0.0'
    author = 'StickyNote'
    description = '统计便签的字符数、词数和行数'

    def on_load(self):
        self.register_context_menu('📊 字数统计', self.show_word_count)
        self.register_tray_menu_item('📊 字数统计', self.show_word_count_tray)

    def show_word_count(self, note_id: int = None):
        """显示当前便签的字数统计"""
        if note_id is None:
            note_id = self.api.get_current_note_id()
        if note_id is None:
            self.show_notification('字数统计', '请先打开一个便签')
            return

        content = self.api.get_note_content(note_id)
        title = self.api.get_note_title(note_id)

        char_count = len(content)
        char_no_space = len(content.replace(' ', '').replace('\n', '').replace('\t', ''))
        word_count = len(content.split()) if content.strip() else 0
        line_count = content.count('\n') + 1
        paragraph_count = len([p for p in content.split('\n\n') if p.strip()]) if content.strip() else 0

        message = (
            f'📊 便签: {title}\n\n'
            f'字符总数: {char_count}\n'
            f'字符数(不含空格): {char_no_space}\n'
            f'词数: {word_count}\n'
            f'行数: {line_count}\n'
            f'段落数: {paragraph_count}'
        )
        self.show_notification('📊 字数统计', message)

    def show_word_count_tray(self):
        """从托盘菜单调用时显示所有便签统计"""
        note_ids = self.api.get_all_note_ids()
        total_chars = 0
        total_words = 0
        for nid in note_ids:
            content = self.api.get_note_content(nid)
            total_chars += len(content)
            total_words += len(content.split()) if content.strip() else 0

        message = f'📊 总计 {len(note_ids)} 个便签\n字符总数: {total_chars}\n词数总计: {total_words}'
        self.show_notification('📊 字数统计', message)

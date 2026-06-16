# -*- coding: utf-8 -*-
"""
便签链接管理模块

支持 [[便签名称]] 语法创建便签间的内部链接，
维护全局链接索引，支持反向链接查询。
"""

import os
import json
import re
import logging
from typing import List, Dict, Tuple, Set

logger = logging.getLogger(__name__)

# 链接解析正则
LINK_PATTERN = re.compile(r'\[\[([^\]]+)\]\]')


class NoteLinkManager:
    """便签链接管理器"""

    def __init__(self, notes_dir: str):
        self.notes_dir = notes_dir
        self.index_file = os.path.join(notes_dir, 'links_index.json')
        self._index: Dict[str, dict] = {}  # {note_id_str: {outgoing: [...], title: "..."}}
        self.load_index()

    # ── 链接解析 ──────────────────────────────────────────

    @staticmethod
    def parse_links(content: str) -> List[str]:
        """
        从 HTML 或纯文本内容中提取 [[...]] 链接

        Args:
            content: 便签内容（HTML 或纯文本）

        Returns:
            目标标题列表
        """
        # 先从 HTML 中提取纯文本部分
        plain = re.sub(r'<[^>]+>', '', content)
        matches = LINK_PATTERN.findall(plain)
        return list(dict.fromkeys(matches))  # 去重且保序

    @staticmethod
    def render_links_in_text(text: str, available_titles: Set[str]) -> str:
        """
        将纯文本中的 [[Title]] 替换为 HTML 超链接

        Args:
            text: 纯文本内容
            available_titles: 可用的便签标题集合

        Returns:
            替换后的 HTML 字符串
        """
        def replace_link(match):
            title = match.group(1)
            if title in available_titles:
                return f'<a href="note://{title}" style="color: #007acc; text-decoration: underline;">{title}</a>'
            else:
                # 目标不存在的链接用灰色显示
                return f'<span style="color: #999; text-decoration: line-through;">{title}</span>'

        return LINK_PATTERN.sub(replace_link, text)

    # ── 索引管理 ──────────────────────────────────────────

    def update_index(self, note_id: int, note_title: str, outgoing_links: List[str]) -> None:
        """
        更新某便签的出链记录

        Args:
            note_id: 便签 ID
            note_title: 便签标题
            outgoing_links: 该便签中的 [[...]] 链接目标标题列表
        """
        key = str(note_id)
        self._index[key] = {
            'outgoing': outgoing_links,
            'title': note_title,
        }
        self.save_index()

    def remove_note(self, note_id: int) -> None:
        """从索引中移除便签"""
        key = str(note_id)
        if key in self._index:
            del self._index[key]
            self.save_index()

    def get_backlinks(self, note_title: str) -> List[Tuple[int, str]]:
        """
        查询指向指定标题的反向链接

        Args:
            note_title: 目标便签标题

        Returns:
            [(note_id, title), ...] 引用了该标题的便签列表
        """
        backlinks = []
        for note_id_str, data in self._index.items():
            if note_title in data.get('outgoing', []):
                backlinks.append((
                    int(note_id_str),
                    data.get('title', f'便签 {note_id_str}')
                ))
        return backlinks

    def get_all_note_titles(self) -> Set[str]:
        """获取所有已索引便签的标题集合"""
        return {data.get('title', '') for data in self._index.values() if data.get('title')}

    def get_outgoing_links(self, note_id: int) -> List[str]:
        """获取某便签的出链列表"""
        key = str(note_id)
        return self._index.get(key, {}).get('outgoing', [])

    # ── 持久化 ──────────────────────────────────────────

    def save_index(self) -> None:
        """保存链接索引到磁盘"""
        try:
            os.makedirs(os.path.dirname(self.index_file), exist_ok=True)
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f'保存链接索引失败: {e}')

    def load_index(self) -> None:
        """从磁盘加载链接索引"""
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    self._index = json.load(f)
            except Exception as e:
                logger.warning(f'加载链接索引失败: {e}')
                self._index = {}
        else:
            self._index = {}

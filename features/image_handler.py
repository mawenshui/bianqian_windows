# -*- coding: utf-8 -*-
"""
图片处理模块

管理图片插入策略（Base64 嵌入 / 文件引用），
以及孤立图片文件的清理。
"""

import os
import base64
import logging
import shutil
import re
from typing import List

logger = logging.getLogger(__name__)


class ImageHandler:
    """图片插入策略管理器"""

    STRATEGY_BASE64 = 'base64'
    STRATEGY_FILE_REF = 'file_ref'

    def __init__(self, notes_dir: str, strategy: str = 'base64', max_size_kb: int = 500):
        self.notes_dir = notes_dir
        self.strategy = strategy
        self.max_size_kb = max_size_kb

    def get_images_dir(self) -> str:
        """获取图片存储目录"""
        images_dir = os.path.join(self.notes_dir, 'images')
        os.makedirs(images_dir, exist_ok=True)
        return images_dir

    def prepare_image(self, source_path: str, note_id: int) -> dict:
        """
        准备图片数据供插入编辑器

        Returns:
            dict: {'strategy': 'base64'|'file_ref',
                   'data': base64_string | file_path,
                   'mime': 'image/png',
                   'original_name': 'photo.png'}
        """
        if not os.path.exists(source_path):
            return {}

        file_size_kb = os.path.getsize(source_path) / 1024
        if file_size_kb > self.max_size_kb:
            logger.warning(f'图片大小 {file_size_kb:.0f}KB 超过限制 {self.max_size_kb}KB')

        ext = os.path.splitext(source_path)[1].lstrip('.').lower()
        if ext == 'jpg':
            ext = 'jpeg'
        mime = f'image/{ext}'
        original_name = os.path.basename(source_path)

        if self.strategy == self.STRATEGY_BASE64:
            with open(source_path, 'rb') as f:
                img_data = f.read()
            b64 = base64.b64encode(img_data).decode('ascii')
            return {
                'strategy': 'base64',
                'data': b64,
                'mime': mime,
                'original_name': original_name,
            }
        else:
            # 文件引用策略
            dest_name = f'note_{note_id}_{original_name}'
            dest_path = os.path.join(self.get_images_dir(), dest_name)
            shutil.copy2(source_path, dest_path)
            return {
                'strategy': 'file_ref',
                'data': dest_path,
                'mime': mime,
                'original_name': original_name,
            }

    def cleanup_orphan_images(self, all_note_contents: List[str]) -> int:
        """
        清理不再被任何便签引用的孤立图片文件

        Args:
            all_note_contents: 所有便签的 HTML 内容列表

        Returns:
            清理的文件数量
        """
        images_dir = self.get_images_dir()
        if not os.path.exists(images_dir):
            return 0

        # 收集所有被引用的图片文件名
        referenced = set()
        for content in all_note_contents:
            # 匹配文件引用路径中的图片文件名
            matches = re.findall(r'images/([^"\'<>\s]+)', content)
            referenced.update(matches)

        # 清理未引用的文件
        cleaned = 0
        for filename in os.listdir(images_dir):
            if filename not in referenced:
                file_path = os.path.join(images_dir, filename)
                try:
                    os.remove(file_path)
                    cleaned += 1
                    logger.debug(f'清理孤立图片: {filename}')
                except OSError as e:
                    logger.warning(f'清理图片失败: {filename} - {e}')

        return cleaned

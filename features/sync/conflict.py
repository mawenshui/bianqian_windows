# -*- coding: utf-8 -*-
"""
冲突检测与解决模块
"""

import os
import shutil
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ConflictResolver:
    """冲突解决器"""

    STRATEGY_NEWER = 'newer'
    STRATEGY_LOCAL = 'local'
    STRATEGY_REMOTE = 'remote'
    STRATEGY_BOTH = 'both'

    @staticmethod
    def resolve(local_path: str, remote_path: str, strategy: str = 'newer') -> str:
        """
        解决文件冲突

        Args:
            local_path: 本地文件路径
            remote_path: 远端文件路径（临时下载位置）
            strategy: 解决策略

        Returns:
            胜出的文件路径
        """
        if strategy == ConflictResolver.STRATEGY_LOCAL:
            return local_path
        elif strategy == ConflictResolver.STRATEGY_REMOTE:
            return remote_path
        elif strategy == ConflictResolver.STRATEGY_NEWER:
            # 比较修改时间
            local_mtime = os.path.getmtime(local_path) if os.path.exists(local_path) else 0
            remote_mtime = os.path.getmtime(remote_path) if os.path.exists(remote_path) else 0
            if local_mtime >= remote_mtime:
                return local_path
            else:
                return remote_path
        elif strategy == ConflictResolver.STRATEGY_BOTH:
            # 保留两个版本，创建冲突副本
            return local_path  # 调用方需要额外创建 conflict copy
        else:
            return local_path

    @staticmethod
    def create_conflict_copy(file_path: str, source: str) -> str:
        """
        创建冲突副本文件

        Args:
            file_path: 原始文件路径
            source: 'local' 或 'remote'

        Returns:
            冲突副本文件路径
        """
        base, ext = os.path.splitext(file_path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        conflict_path = f'{base}.conflict_{source}_{timestamp}{ext}'
        try:
            shutil.copy2(file_path, conflict_path)
            logger.info(f'创建冲突副本: {conflict_path}')
        except Exception as e:
            logger.error(f'创建冲突副本失败: {e}')
        return conflict_path

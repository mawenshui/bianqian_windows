# -*- coding: utf-8 -*-
"""
统一日志系统模块

提供集中的日志管理，支持：
- DEBUG/INFO: 写入文件
- WARNING: 写入文件 + 控制台
- ERROR: 写入文件 + 控制台 + QMessageBox（可选）
- 日志文件自动轮转（RotatingFileHandler，最大 5MB，保留 3 个备份）
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

from core import get_project_root

# 日志文件路径 — 始终放在软件所在目录的 logs/ 下
LOG_DIR = os.path.join(get_project_root(), 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'sticky_note.log')

# 日志格式
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# 是否已初始化全局日志配置
_initialized = False

# 保存 root logger 的引用，供 show_error 使用
_root_logger: Optional[logging.Logger] = None


def setup_logging(log_level: int = logging.DEBUG) -> logging.Logger:
    """
    初始化全局日志系统（幂等，多次调用仅生效一次）。

    Args:
        log_level: 文件日志最低级别，默认 DEBUG

    Returns:
        root logger
    """
    global _initialized, _root_logger

    if _initialized:
        return logging.getLogger()

    os.makedirs(LOG_DIR, exist_ok=True)

    # Root logger — 捕获所有级别
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # 文件 Handler（DEBUG 及以上写入文件，自动轮转）
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(file_handler)

    # 控制台 Handler（WARNING 及以上输出到 stderr）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(console_handler)

    _initialized = True
    _root_logger = root

    root.info('日志系统初始化完成')
    return root


def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的 logger。

    Args:
        name: logger 名称（通常传 __name__）

    Returns:
        配置好的 logger 实例
    """
    # 确保日志系统已初始化
    if not _initialized:
        setup_logging()

    return logging.getLogger(name)


def show_error(title: str, message: str) -> None:
    """
    显示用户可见的错误对话框（用于 ERROR 级别）。

    Args:
        title: 对话框标题
        message: 错误消息内容
    """
    try:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.warning(None, title, message)
    except Exception:
        # 如果 Qt 尚未初始化，回退到控制台输出
        print(f'[ERROR] {title}: {message}')


# 模块初始化时自动配置
setup_logging()

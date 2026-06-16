# -*- coding: utf-8 -*-
"""
统一异常层次结构模块

定义应用级异常类和分层错误处理策略，替代代码中四种不一致模式：
- 静默吞掉 (except Exception: pass)
- 只打日志 (logger.error/warning)
- 弹窗提示 (QMessageBox)
- 重新抛出 (raise RuntimeError)

策略分层：
  UI 层  → QMessageBox 弹窗（用户可见）
  业务层 → logger 日志记录
  底层   → raise 让调用方决策
  插件层 → 捕获后日志，禁止崩溃
"""

import logging
from typing import Optional
from PyQt5.QtWidgets import QMessageBox, QWidget

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 异常层次结构
# ═══════════════════════════════════════════════════════════════

class StickyNoteError(Exception):
    """应用基础异常 — 所有自定义异常的父类"""

    def __init__(self, message: str, original: Optional[Exception] = None):
        super().__init__(message)
        self.user_message = message
        self.original = original


class DataError(StickyNoteError):
    """数据层异常 — 数据损坏、格式错误、验证失败等"""


class FileOperationError(StickyNoteError):
    """文件操作异常 — 读写失败、权限不足等"""


class ConfigurationError(StickyNoteError):
    """配置异常 — 配置项缺失、类型错误、迁移失败等"""


class PluginError(StickyNoteError):
    """
    插件层异常 — 插件故障不应导致主应用崩溃。
    调用方必须捕获此异常，禁止向上传播到 UI 主循环。
    """


class SearchError(StickyNoteError):
    """搜索异常 — 索引构建失败、搜索执行错误等"""


# ═══════════════════════════════════════════════════════════════
# 统一错误处理
# ═══════════════════════════════════════════════════════════════

def handle_error(
    error: Exception,
    context: str = 'general',
    show_ui: bool = False,
    parent: Optional[QWidget] = None
) -> None:
    """
    统一错误处理入口。

    Args:
        error: 捕获的异常
        context: 错误上下文标识（如 'save_note', 'load_config'）
        show_ui: 是否弹窗提示用户（UI 层）
        parent: 弹窗的父窗口
    """
    if isinstance(error, PluginError):
        # 插件异常：仅日志，静默处理
        logger.debug(f'[Plugin] {context}: {error}', exc_info=False)
        return

    if show_ui:
        # UI 层：弹窗提示用户
        msg = getattr(error, 'user_message', None) or str(error)
        QMessageBox.warning(parent, '错误', f'操作失败 ({context}):\n{msg}')
        logger.warning(f'[UI] {context}: {error}', exc_info=False)
    else:
        # 业务层：日志记录
        if isinstance(error, (DataError, FileOperationError, ConfigurationError)):
            logger.error(f'[{context}] {error}', exc_info=True)
        else:
            logger.warning(f'[{context}] {error}', exc_info=False)

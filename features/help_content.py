# -*- coding: utf-8 -*-
"""
帮助内容模块

动态读取 readme.md 并转换为 HTML，供帮助对话框使用。
当 readme.md 更新时，帮助页面内容自动同步，无需手动维护。
"""

import os
import logging

from core import get_project_root, __version__

logger = logging.getLogger(__name__)

# 缓存已渲染的 HTML
_cached_full_html = None
_cached_quick_text = None


def _find_readme() -> str:
    """查找 readme.md 文件路径"""
    candidates = [
        os.path.join(get_project_root(), 'readme.md'),
        os.path.join(get_project_root(), 'README.md'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'readme.md'),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ''


def _read_readme() -> str:
    """读取 readme.md 内容"""
    path = _find_readme()
    if not path:
        return ''
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.warning(f'读取 readme.md 失败: {e}')
        return ''


def get_full_help_html() -> str:
    """
    获取完整帮助 HTML（从 readme.md 渲染）。

    使用 MarkdownRenderer 将 readme.md 转换为 HTML，
    供 QTextBrowser 通过 setDefaultStyleSheet + setHtml 显示。

    Returns:
        str: 渲染后的 HTML 字符串（body 内容）
    """
    global _cached_full_html
    if _cached_full_html:
        return _cached_full_html

    md_text = _read_readme()
    if not md_text:
        _cached_full_html = _fallback_html()
        return _cached_full_html

    try:
        from features.markdown_renderer import MarkdownRenderer
        renderer = MarkdownRenderer()
        html = renderer.render_body_only(md_text)
        _cached_full_html = html
        return html
    except Exception as e:
        logger.warning(f'Markdown 渲染失败: {e}')
        _cached_full_html = _fallback_html()
        return _cached_full_html


def get_help_css() -> str:
    """
    获取 Markdown 渲染用的 CSS 样式表。

    用于 QTextBrowser.document().setDefaultStyleSheet()。

    Returns:
        str: CSS 样式表字符串
    """
    try:
        from features.markdown_renderer import MarkdownRenderer
        return MarkdownRenderer.DOCUMENT_CSS
    except Exception:
        return ''


def get_quick_help_text() -> str:
    """
    获取便签快速帮助文本（精简版）。

    用于便签 "?" 按钮的 QMessageBox 显示。

    Returns:
        str: 精简版纯文本帮助内容
    """
    global _cached_quick_text
    if _cached_quick_text:
        return _cached_quick_text

    _cached_quick_text = (
        '📝 便签使用说明\n\n'
        '📌 基本操作\n'
        '  • 拖拽空白区域移动便签，边缘拖拽调整大小\n'
        '  • 拖拽到屏幕边缘松手可贴边自动隐藏\n'
        '  • 点击 × 按钮隐藏到托盘（不关闭）\n'
        '  • 右键菜单可切换主题、设置字体等\n\n'
        '✏️ 文字格式（需先选中文字）\n'
        '  • A+/A-：字体大小  • B：加粗  • I：斜体\n'
        '  • U：下划线  • S：删除线  • A(颜色)：字体颜色\n'
        '  • x²/x₂：上标/下标  • ⇤/≡/⇥：对齐\n'
        '  • 1./•：有序/无序列表  • 🖍/✖：高亮/清除\n\n'
        '🔧 功能按钮\n'
        '  • ↩/↪：撤销/重做  • 🏷：标签  • ⏰：提醒\n'
        '  • 🔓/🔒：锁定/解锁  • 🔗：链接  • 🖼：图片\n'
        '  • MD：Markdown 预览  • 🔙：反向链接\n\n'
        '⌨ 快捷键\n'
        '  • Ctrl+Shift+N：新建便签（全局）\n'
        '  • Ctrl+Shift+F：搜索便签（全局）\n'
        '  • Ctrl+Shift+B：备份管理（全局）\n'
        '  • Ctrl+F：便签内搜索  • Ctrl+Z/Y：撤销/重做\n\n'
        f'📖 完整说明：托盘图标右键 → 帮助（v{__version__}）'
    )
    return _cached_quick_text


def invalidate_cache():
    """清除缓存，下次调用时重新读取和渲染"""
    global _cached_full_html, _cached_quick_text
    _cached_full_html = None
    _cached_quick_text = None


def _fallback_html() -> str:
    """readme.md 不可用时的回退 HTML"""
    return f'''
<h2>📝 桌面便签 — 使用说明</h2>
<p style="color:#888; font-size:10pt;">当前版本: v{__version__} | 作者: MaWenshui</p>

<h3>📌 基本操作</h3>
<ul>
  <li><b>拖拽移动：</b>按住便签空白区域拖拽可移动位置</li>
  <li><b>缩放调整：</b>鼠标移到便签边缘会出现双向箭头，拖拽即可调整大小</li>
  <li><b>贴边隐藏：</b>拖拽到屏幕边缘松手自动隐藏，留下标签页，悬停/点击恢复</li>
  <li><b>关闭/隐藏：</b>点击 × 隐藏到托盘，不会丢失数据</li>
</ul>

<h3>✏️ 文字格式（需先选中文字）</h3>
<ul>
  <li><b>A+/A-：</b>增大/减小字号  <b>B：</b>加粗  <b>I：</b>斜体</li>
  <li><b>U：</b>下划线  <b>S：</b>删除线  <b>A(颜色)：</b>字体颜色</li>
  <li><b>x²/x₂：</b>上标/下标  <b>⇤/≡/⇥：</b>左/中/右对齐</li>
  <li><b>1./•：</b>有序/无序列表  <b>🖍/✖：</b>高亮/清除高亮</li>
</ul>

<h3>🔧 功能按钮</h3>
<ul>
  <li><b>↩/↪：</b>撤销/重做  <b>🏷：</b>标签  <b>⏰：</b>定时提醒</li>
  <li><b>🔓/🔒：</b>锁定/解锁  <b>🔗：</b>插入链接  <b>🖼：</b>插入图片</li>
  <li><b>MD：</b>Markdown 预览  <b>🔙：</b>反向链接</li>
</ul>

<h3>🎨 主题与外观</h3>
<ul>
  <li>内置 15 款主题，右键菜单可切换。自定义 CSS 保存到 styles/ 目录后自动加载</li>
  <li>勾选"总在最前"使便签始终置顶</li>
</ul>

<h3>⌨ 快捷键</h3>
<ul>
  <li><b>Ctrl+Shift+N：</b>全局新建  <b>Ctrl+Shift+F：</b>搜索  <b>Ctrl+Shift+B：</b>备份</li>
  <li><b>Ctrl+F：</b>便签内搜索  <b>Ctrl+Z/Y：</b>撤销/重做</li>
</ul>

<h3>🔒 主密码保护</h3>
<ul>
  <li>设置 → 安全 → 启用主密码，启动时需输入密码验证</li>
  <li>禁用时需先验证当前密码</li>
</ul>

<p style="color:#888;">提示：完整使用说明请查看项目 readme.md 文件</p>
'''

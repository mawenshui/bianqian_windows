# -*- coding: utf-8 -*-
"""
Markdown 渲染模块

使用 markdown 库将 Markdown 文本转换为 HTML，
支持表格、代码块、目录等扩展语法。
"""

import logging

logger = logging.getLogger(__name__)

# 尝试导入 markdown 库
try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False
    logger.warning('markdown 库未安装，Markdown 渲染功能不可用。请运行: pip install markdown')

# 可选的 Pygments 代码高亮
try:
    import pygments
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False


class MarkdownRenderer:
    """Markdown → HTML 渲染器"""

    @staticmethod
    def _preprocess(text: str) -> str:
        """预处理 Markdown 文本，补充 markdown 库不支持的语法"""
        import re
        # ~~text~~ → <del>text</del> (删除线)
        text = re.sub(r'~~(.+?)~~', r'<del>\1</del>', text)
        return text

    # QTextBrowser document 默认样式表（不含 <style> 标签，直接用于 setDefaultStyleSheet）
    DOCUMENT_CSS = """
        body { font-family: "Microsoft YaHei", sans-serif; font-size: 12pt; line-height: 1.6; color: #333; padding: 8px; }
        h1 { font-size: 1.8em; border-bottom: 2px solid #ddd; padding-bottom: 4px; margin: 12px 0 8px 0; }
        h2 { font-size: 1.5em; border-bottom: 1px solid #ddd; padding-bottom: 3px; margin: 10px 0 6px 0; }
        h3 { font-size: 1.3em; margin: 8px 0 4px 0; }
        h4 { font-size: 1.1em; margin: 6px 0 4px 0; }
        strong, b { font-weight: bold; }
        em, i { font-style: italic; }
        del, s { text-decoration: line-through; color: #999; }
        code { background-color: #f4f4f4; padding: 2px 4px; border-radius: 3px; font-family: Consolas, monospace; font-size: 0.9em; }
        pre { background-color: #f4f4f4; padding: 12px; border-radius: 4px; overflow-x: auto; }
        pre code { background-color: transparent; padding: 0; }
        blockquote { border-left: 4px solid #ddd; margin: 4px 0; padding-left: 16px; color: #666; }
        table { border-collapse: collapse; width: 100%; margin: 8px 0; }
        th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }
        th { background-color: #f0f0f0; font-weight: bold; }
        img { max-width: 100%; height: auto; }
        a { color: #007acc; text-decoration: underline; }
        hr { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
        ul { padding-left: 24px; list-style-type: disc; margin: 8px 0; }
        ol { padding-left: 24px; list-style-type: decimal; margin: 8px 0; }
        li { margin: 4px 0; display: list-item; }
        p { margin: 6px 0; }
    """

    # 用于 setHtml() 的 <style> 包装（备用）
    PREVIEW_CSS = f"""
    <style>{DOCUMENT_CSS}</style>
    """

    def __init__(self):
        self.extensions = ['tables', 'fenced_code', 'toc', 'nl2br', 'sane_lists']
        # 尝试添加删除线支持
        try:
            import markdown.extensions.smarty  # noqa: F401
            # 部分版本使用 'md_in_html' 或 'extra' 包含 del 支持
        except ImportError:
            pass
        if HAS_PYGMENTS:
            self.extensions.append('codehilite')

    def render(self, markdown_text: str) -> str:
        """
        将 Markdown 文本渲染为带样式的完整 HTML 字符串

        Args:
            markdown_text: Markdown 源文本

        Returns:
            完整的 HTML 字符串（含 <html> 标签和 CSS）
        """
        markdown_text = self._preprocess(markdown_text)
        if not HAS_MARKDOWN:
            return f'<html><body><pre>{markdown_text}</pre></body></html>'

        try:
            body_html = markdown.markdown(
                markdown_text,
                extensions=self.extensions,
                output_format='html5'
            )
            return f'<html><head>{self.PREVIEW_CSS}</head><body>{body_html}</body></html>'
        except Exception as e:
            logger.error(f'Markdown 渲染失败: {e}')
            return f'<html><body><pre>{markdown_text}</pre></body></html>'

    def render_for_qt(self, markdown_text: str) -> tuple:
        """
        专为 QTextBrowser 渲染 Markdown

        返回 (body_html, css) 元组，调用方应使用：
            browser.document().setDefaultStyleSheet(css)
            browser.setHtml(body_html)

        这种方式比 setHtml() 包含 <head><style> 更可靠。
        """
        markdown_text = self._preprocess(markdown_text)
        if not HAS_MARKDOWN:
            return f'<pre>{markdown_text}</pre>', self.DOCUMENT_CSS
        try:
            body_html = markdown.markdown(
                markdown_text,
                extensions=self.extensions,
                output_format='html5'
            )
            return body_html, self.DOCUMENT_CSS
        except Exception as e:
            logger.error(f'Markdown 渲染失败: {e}')
            return f'<pre>{markdown_text}</pre>', self.DOCUMENT_CSS

    def render_body_only(self, markdown_text: str) -> str:
        """渲染为纯 body HTML（不含 <html> 和 CSS 包装）"""
        markdown_text = self._preprocess(markdown_text)
        if not HAS_MARKDOWN:
            return f'<pre>{markdown_text}</pre>'
        try:
            return markdown.markdown(
                markdown_text,
                extensions=self.extensions,
                output_format='html5'
            )
        except Exception as e:
            logger.error(f'Markdown 渲染失败: {e}')
            return f'<pre>{markdown_text}</pre>'

    @staticmethod
    def is_available() -> bool:
        """检查 markdown 库是否可用"""
        return HAS_MARKDOWN

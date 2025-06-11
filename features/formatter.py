# -*- coding: utf-8 -*-
"""
内容格式化模块

提供智能内容识别和格式化功能，支持JSON、HTML、Markdown等格式
"""

import json
import re
import html
from typing import Tuple, Optional
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtGui import QTextCharFormat, QColor, QFont, QTextCursor


class ContentFormatter(QObject):
    """
    内容格式化器
    
    自动识别和格式化不同类型的内容
    """
    
    def __init__(self):
        super().__init__()
        self.format_handlers = {
            'json': self._format_json,
            'html': self._format_html,
            'markdown': self._format_markdown,
            'xml': self._format_xml,
            'css': self._format_css,
            'javascript': self._format_javascript,
            'python': self._format_python,
            'sql': self._format_sql
        }
    
    def detect_content_type(self, content: str) -> str:
        """
        检测内容类型
        
        Args:
            content: 要检测的内容
            
        Returns:
            检测到的内容类型
        """
        content = content.strip()
        
        if not content:
            return 'plain'
        
        # JSON检测
        if self._is_json(content):
            return 'json'
        
        # HTML检测
        if self._is_html(content):
            return 'html'
        
        # XML检测
        if self._is_xml(content):
            return 'xml'
        
        # Markdown检测
        if self._is_markdown(content):
            return 'markdown'
        
        # CSS检测
        if self._is_css(content):
            return 'css'
        
        # JavaScript检测
        if self._is_javascript(content):
            return 'javascript'
        
        # Python检测
        if self._is_python(content):
            return 'python'
        
        # SQL检测
        if self._is_sql(content):
            return 'sql'
        
        return 'plain'
    
    def format_content(self, content: str, content_type: str = None) -> Tuple[str, str]:
        """
        格式化内容
        
        Args:
            content: 要格式化的内容
            content_type: 内容类型，如果为None则自动检测
            
        Returns:
            (格式化后的内容, 内容类型)
        """
        if content_type is None:
            content_type = self.detect_content_type(content)
        
        if content_type in self.format_handlers:
            formatted_content = self.format_handlers[content_type](content)
            return formatted_content, content_type
        
        return content, 'plain'
    
    def _is_json(self, content: str) -> bool:
        """检测是否为JSON格式"""
        try:
            json.loads(content)
            return True
        except (json.JSONDecodeError, ValueError):
            return False
    
    def _is_html(self, content: str) -> bool:
        """检测是否为HTML格式"""
        html_patterns = [
            r'<\s*html[^>]*>',
            r'<\s*head[^>]*>',
            r'<\s*body[^>]*>',
            r'<\s*div[^>]*>',
            r'<\s*p[^>]*>',
            r'<\s*span[^>]*>',
            r'<!DOCTYPE\s+html'
        ]
        
        for pattern in html_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        # 检查是否包含多个HTML标签
        tag_count = len(re.findall(r'<[^>]+>', content))
        return tag_count >= 2
    
    def _is_xml(self, content: str) -> bool:
        """检测是否为XML格式"""
        xml_patterns = [
            r'<\?xml[^>]*\?>',
            r'<\s*[a-zA-Z][^>]*>.*</\s*[a-zA-Z][^>]*>'
        ]
        
        for pattern in xml_patterns:
            if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                return True
        
        return False
    
    def _is_markdown(self, content: str) -> bool:
        """检测是否为Markdown格式"""
        md_patterns = [
            r'^#{1,6}\s+',  # 标题
            r'^\*\s+',      # 无序列表
            r'^\d+\.\s+',  # 有序列表
            r'\*\*[^*]+\*\*',  # 粗体
            r'\*[^*]+\*',     # 斜体
            r'`[^`]+`',       # 行内代码
            r'^```',          # 代码块
            r'\[([^\]]+)\]\(([^)]+)\)',  # 链接
            r'^>\s+'          # 引用
        ]
        
        for pattern in md_patterns:
            if re.search(pattern, content, re.MULTILINE):
                return True
        
        return False
    
    def _is_css(self, content: str) -> bool:
        """检测是否为CSS格式"""
        css_patterns = [
            r'[a-zA-Z#.][^{]*\s*{[^}]*}',  # CSS规则
            r'@media[^{]*{',               # 媒体查询
            r'@import[^;]*;',              # 导入语句
        ]
        
        for pattern in css_patterns:
            if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                return True
        
        return False
    
    def _is_javascript(self, content: str) -> bool:
        """检测是否为JavaScript格式"""
        js_patterns = [
            r'\bfunction\s+\w+\s*\(',
            r'\bvar\s+\w+\s*=',
            r'\blet\s+\w+\s*=',
            r'\bconst\s+\w+\s*=',
            r'\bconsole\.log\s*\(',
            r'\bdocument\.',
            r'\bwindow\.',
            r'=>\s*{',
        ]
        
        for pattern in js_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    
    def _is_python(self, content: str) -> bool:
        """检测是否为Python格式"""
        py_patterns = [
            r'\bdef\s+\w+\s*\(',
            r'\bclass\s+\w+\s*[:(]',
            r'\bimport\s+\w+',
            r'\bfrom\s+\w+\s+import',
            r'\bif\s+__name__\s*==\s*["\']__main__["\']',
            r'\bprint\s*\(',
            r'#.*$',  # Python注释
        ]
        
        for pattern in py_patterns:
            if re.search(pattern, content, re.MULTILINE):
                return True
        
        return False
    
    def _is_sql(self, content: str) -> bool:
        """检测是否为SQL格式"""
        sql_patterns = [
            r'\bSELECT\s+',
            r'\bINSERT\s+INTO\s+',
            r'\bUPDATE\s+\w+\s+SET\s+',
            r'\bDELETE\s+FROM\s+',
            r'\bCREATE\s+TABLE\s+',
            r'\bALTER\s+TABLE\s+',
            r'\bDROP\s+TABLE\s+',
        ]
        
        for pattern in sql_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    
    def _format_json(self, content: str) -> str:
        """格式化JSON内容"""
        try:
            parsed = json.loads(content)
            formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
            return f"[JSON格式]\n{formatted}"
        except (json.JSONDecodeError, ValueError):
            return content
    
    def _format_html(self, content: str) -> str:
        """格式化HTML内容"""
        # 简单的HTML格式化
        formatted = content
        
        # 添加缩进
        lines = formatted.split('\n')
        indent_level = 0
        formatted_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 减少缩进（闭合标签）
            if re.match(r'</\w+>', line):
                indent_level = max(0, indent_level - 1)
            
            formatted_lines.append('  ' * indent_level + line)
            
            # 增加缩进（开放标签）
            if re.match(r'<\w+[^>]*>(?!</\w+>)', line) and not line.endswith('/>'):
                indent_level += 1
        
        formatted_content = '\n'.join(formatted_lines)
        return f"[HTML格式]\n{formatted_content}"
    
    def _format_markdown(self, content: str) -> str:
        """格式化Markdown内容"""
        return f"[Markdown格式]\n{content}"
    
    def _format_xml(self, content: str) -> str:
        """格式化XML内容"""
        return f"[XML格式]\n{content}"
    
    def _format_css(self, content: str) -> str:
        """格式化CSS内容"""
        return f"[CSS格式]\n{content}"
    
    def _format_javascript(self, content: str) -> str:
        """格式化JavaScript内容"""
        return f"[JavaScript格式]\n{content}"
    
    def _format_python(self, content: str) -> str:
        """格式化Python内容"""
        return f"[Python格式]\n{content}"
    
    def _format_sql(self, content: str) -> str:
        """格式化SQL内容"""
        return f"[SQL格式]\n{content}"


class SmartTextEdit(QTextEdit):
    """
    智能文本编辑器
    
    支持自动格式化粘贴内容
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.formatter = ContentFormatter()
        self.auto_format_enabled = True
    
    def set_auto_format_enabled(self, enabled: bool):
        """设置是否启用自动格式化"""
        self.auto_format_enabled = enabled
    
    def insertFromMimeData(self, source):
        """重写粘贴方法以支持智能格式化"""
        if source.hasText() and self.auto_format_enabled:
            text = source.text()
            formatted_text, content_type = self.formatter.format_content(text)
            
            if content_type != 'plain':
                # 插入格式化后的内容
                self.insertPlainText(formatted_text)
            else:
                # 普通文本直接插入
                self.insertPlainText(text)
        else:
            super().insertFromMimeData(source)
    
    def paste(self):
        """重写粘贴方法"""
        from PyQt5.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        
        if self.auto_format_enabled:
            text = clipboard.text()
            formatted_text, content_type = self.formatter.format_content(text)
            
            if content_type != 'plain':
                self.insertPlainText(formatted_text)
            else:
                self.insertPlainText(text)
        else:
            self.insertPlainText(clipboard.text())
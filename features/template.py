# -*- coding: utf-8 -*-
"""
便签模板系统模块

支持：
- 内置模板：待办清单、会议纪要、周计划
- 用户自定义模板
- 基于模板快速创建便签
- 模板管理界面
"""

import os
import json

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QTextEdit, QLineEdit,
    QMessageBox, QInputDialog, QSplitter, QFrame
)
from PyQt5.QtCore import Qt

# 内置模板
BUILTIN_TEMPLATES = {
    "todo": {
        "name": "待办清单",
        "icon": "✅",
        "content": "# 待办清单\n\n- [ ] 任务一\n- [ ] 任务二\n- [ ] 任务三\n\n---\n*创建于 {date}*"
    },
    "meeting": {
        "name": "会议纪要",
        "icon": "📋",
        "content": "# 会议纪要\n\n**日期**：{date}\n**参会人**：\n\n## 议题\n\n1. \n\n## 决议\n\n- \n\n## 待办\n\n- [ ] \n"
    },
    "weekplan": {
        "name": "周计划",
        "icon": "📅",
        "content": "# 周计划 ({date})\n\n## 周一\n- \n\n## 周二\n- \n\n## 周三\n- \n\n## 周四\n- \n\n## 周五\n- \n\n## 本周目标\n- \n"
    },
    "daily": {
        "name": "每日日志",
        "icon": "📝",
        "content": "# {date}\n\n## 今日计划\n- \n\n## 实际完成\n- \n\n## 备注\n"
    },
    "brainstorm": {
        "name": "头脑风暴",
        "icon": "💡",
        "content": "# 头脑风暴\n\n**主题**：\n\n## 想法\n\n- \n\n## 行动项\n\n- [ ] \n"
    },
}


class TemplateManager:
    """
    模板管理器

    管理内置和自定义模板，存储到 templates/ 目录。
    """

    def __init__(self, manager):
        self.manager = manager
        self.templates_dir = os.path.join(
            os.path.dirname(manager.settings_file), 'templates'
        )
        os.makedirs(self.templates_dir, exist_ok=True)
        self.custom_templates: dict = self.load_custom_templates()

    def load_custom_templates(self) -> dict:
        result = {}
        if os.path.exists(self.templates_dir):
            for filename in os.listdir(self.templates_dir):
                if filename.endswith('.json'):
                    try:
                        with open(os.path.join(self.templates_dir, filename), 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        key = filename[:-5]
                        result[key] = data
                    except Exception as e:
                        print(f"[TemplateManager] 加载模板失败 {filename}: {e}")
        return result

    def save_custom_template(self, key: str, data: dict):
        filepath = os.path.join(self.templates_dir, f'{key}.json')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.custom_templates[key] = data

    def delete_custom_template(self, key: str):
        filepath = os.path.join(self.templates_dir, f'{key}.json')
        if os.path.exists(filepath):
            os.remove(filepath)
        self.custom_templates.pop(key, None)

    def get_all_templates(self) -> dict:
        """返回所有模板（内置 + 自定义）"""
        all_templates = {}
        # 内置
        for key, data in BUILTIN_TEMPLATES.items():
            all_templates[key] = data
        # 自定义
        for key, data in self.custom_templates.items():
            all_templates[key] = data
        return all_templates

    def create_note_from_template(self, template_key: str):
        """基于模板创建便签"""
        templates = self.get_all_templates()
        if template_key not in templates:
            return None

        template = templates[template_key]
        from datetime import datetime
        date_str = datetime.now().strftime('%Y-%m-%d')

        title = template.get('name', '新便签')
        content = template.get('content', '').replace('{date}', date_str)

        # 创建便签
        note_id = self.manager.generate_note_id()
        default_theme = self.manager.get_default_theme_css()
        note = self.manager.notes.get(note_id)  # not yet added
        from core.note import StickyNote
        note = StickyNote(note_id, self.manager.notes_dir, manager=self.manager, theme_css=default_theme)

        # 应用模板
        note.title_edit.setText(title)
        note.text_edit.setPlainText(content)
        note.note_data['title'] = title
        note.note_data['content'] = content
        note.note_data['template'] = template_key

        note.show()
        self.manager.notes[note_id] = note
        self.manager.update_tray_menu()
        return note


class TemplateDialog(QDialog):
    """模板选择和编辑对话框"""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.template_manager = manager.template_manager if hasattr(manager, 'template_manager') else TemplateManager(manager)
        self.setWindowTitle('便签模板')
        self.setFixedSize(650, 450)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout()

        # 左侧：模板列表
        left = QVBoxLayout()

        left_label = QLabel('📄 模板列表')
        left_label.setStyleSheet('font-size: 12pt; font-weight: bold;')
        left.addWidget(left_label)

        self.template_list = QListWidget()
        self.refresh_list()
        self.template_list.currentRowChanged.connect(self.on_template_selected)
        left.addWidget(self.template_list)

        # 模板操作
        btn_layout = QHBoxLayout()
        use_btn = QPushButton('使用模板')
        use_btn.clicked.connect(self.use_template)
        delete_btn = QPushButton('删除')
        delete_btn.clicked.connect(self.delete_template)
        btn_layout.addWidget(use_btn)
        btn_layout.addWidget(delete_btn)
        left.addLayout(btn_layout)

        layout.addLayout(left)

        # 右侧：预览 + 自定义
        right = QVBoxLayout()

        right_label = QLabel('📝 模板预览 / 自定义')
        right_label.setStyleSheet('font-size: 12pt; font-weight: bold;')
        right.addWidget(right_label)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel('名称:'))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText('模板名称...')
        name_layout.addWidget(self.name_edit)
        right.addLayout(name_layout)

        self.preview_edit = QTextEdit()
        self.preview_edit.setPlaceholderText('模板内容（支持 {date} 占位符）...')
        right.addWidget(self.preview_edit)

        save_btn = QPushButton('保存为自定义模板')
        save_btn.clicked.connect(self.save_custom)
        right.addWidget(save_btn)

        layout.addLayout(right)
        self.setLayout(layout)

    def refresh_list(self):
        self.template_list.clear()
        templates = self.template_manager.get_all_templates()
        builtin_keys = set(BUILTIN_TEMPLATES.keys())
        for key, data in templates.items():
            icon = data.get('icon', '📄')
            name = data.get('name', key)
            display = f'{icon}  {name}'
            if key not in builtin_keys:
                display += ' (自定义)'
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, key)
            self.template_list.addItem(item)

    def on_template_selected(self, row):
        if row < 0:
            return
        key = self.template_list.item(row).data(Qt.UserRole)
        templates = self.template_manager.get_all_templates()
        if key in templates:
            data = templates[key]
            self.name_edit.setText(data.get('name', ''))
            self.preview_edit.setPlainText(data.get('content', ''))

    def use_template(self):
        row = self.template_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, '提示', '请选择一个模板')
            return
        key = self.template_list.item(row).data(Qt.UserRole)
        note = self.template_manager.create_note_from_template(key)
        if note:
            QMessageBox.information(self, '创建成功', f'已基于模板创建便签: {note.note_data.get("title", "")}')

    def save_custom(self):
        name = self.name_edit.text().strip()
        content = self.preview_edit.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, '提示', '请输入模板名称')
            return
        if not content:
            QMessageBox.warning(self, '提示', '请输入模板内容')
            return

        # 生成 key
        import re
        key = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())[:30]
        if key in BUILTIN_TEMPLATES:
            key += '_custom'

        data = {
            'name': name,
            'icon': '📄',
            'content': content,
        }
        self.template_manager.save_custom_template(key, data)
        self.refresh_list()
        QMessageBox.information(self, '保存成功', f'模板 "{name}" 已保存')

    def delete_template(self):
        row = self.template_list.currentRow()
        if row < 0:
            return
        key = self.template_list.item(row).data(Qt.UserRole)
        if key in BUILTIN_TEMPLATES:
            QMessageBox.warning(self, '无法删除', '内置模板不可删除')
            return

        reply = QMessageBox.question(self, '确认删除', f'确定删除此模板？', QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.template_manager.delete_custom_template(key)
            self.refresh_list()
            self.name_edit.clear()
            self.preview_edit.clear()

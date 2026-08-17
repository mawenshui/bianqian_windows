# -*- coding: utf-8 -*-
"""便签核心模块的单元测试"""
import unittest
import tempfile
import os
import shutil
from unittest.mock import MagicMock, patch

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QImage, QColor, QTextCursor
from PyQt5.QtWidgets import QApplication


class TestPlainLineEdit(unittest.TestCase):
    """PlainLineEdit — 纯文本标题编辑器"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_create_line_edit(self):
        """创建 PlainLineEdit 实例"""
        from core.note import PlainLineEdit
        edit = PlainLineEdit()
        self.assertIsNotNone(edit)
        self.assertEqual(edit.maxLength(), 32767)  # QLineEdit 默认

    def test_set_text(self):
        """设置纯文本"""
        from core.note import PlainLineEdit
        edit = PlainLineEdit()
        edit.setText("测试标题")
        self.assertEqual(edit.text(), "测试标题")

    def test_paste_removes_rich_text(self):
        """粘贴时应去除富文本格式（只保留纯文本）"""
        from core.note import PlainLineEdit
        edit = PlainLineEdit()
        # 模拟粘贴：直接调用 paste() 验证不会崩溃
        # paste 方法会从剪贴板获取并转换为纯文本
        edit.paste()  # 不应抛出异常


class TestPlainTextEdit(unittest.TestCase):
    """PlainTextEdit — 纯文本内容编辑器"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_create_text_edit(self):
        """创建 PlainTextEdit 实例"""
        from core.note import PlainTextEdit
        edit = PlainTextEdit()
        self.assertIsNotNone(edit)

    def test_set_text(self):
        """设置文本内容"""
        from core.note import PlainTextEdit
        edit = PlainTextEdit()
        edit.setText("测试内容")
        self.assertEqual(edit.toPlainText(), "测试内容")

    def test_auto_format_toggle(self):
        """智能格式化开关"""
        from core.note import PlainTextEdit
        edit = PlainTextEdit()
        edit.set_auto_format_enabled(True)
        # 设置后不应抛出异常
        edit.set_auto_format_enabled(False)


class TestStickyNoteDefaults(unittest.TestCase):
    """StickyNote — 默认数据和初始化"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_default_note_data_fields(self):
        """default_note_data 应包含所有必要字段"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(999, temp_dir, manager=None)
                data = note.note_data
                # 核心字段
                self.assertIn('title', data)
                self.assertIn('content', data)
                self.assertIn('opacity', data)
                self.assertIn('always_on_top', data)
                self.assertIn('theme', data)
                self.assertEqual(data['background_image'], '')
                self.assertEqual(data['control_opacity'], 1.0)
                self.assertEqual(data['background_text_color'], '')
                self.assertEqual(data['background_control_color'], '')
                self.assertEqual(data['font_color_mode'], 'theme')
                self.assertIn('background_image', data)
                self.assertIn('control_opacity', data)
                self.assertEqual(data['background_image'], '')
                self.assertEqual(data['control_opacity'], 1.0)
                # v1.6.3 新增字段
                self.assertIn('locked', data)
                self.assertIn('pinned', data)
                self.assertIn('favorite', data)
                # 默认值验证
                self.assertFalse(data['locked'])
                self.assertFalse(data['pinned'])
                self.assertFalse(data['favorite'])
                self.assertTrue(data['always_on_top'])
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_note_has_undo_redo_buttons(self):
        """便签应创建撤销/重做按钮"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(998, temp_dir, manager=None)
                self.assertTrue(hasattr(note, 'undo_btn'))
                self.assertTrue(hasattr(note, 'redo_btn'))
                # 初始状态应为禁用
                self.assertFalse(note.undo_btn.isEnabled())
                self.assertFalse(note.redo_btn.isEnabled())
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_note_has_lock_button(self):
        """便签应创建锁定按钮"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(997, temp_dir, manager=None)
                self.assertTrue(hasattr(note, 'lock_btn'))
                self.assertTrue(hasattr(note, 'is_locked'))
                self.assertFalse(note.is_locked)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_background_image_copy_and_control_opacity(self):
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        source = os.path.join(temp_dir, 'source.png')
        QImage(12, 8, QImage.Format_RGB32).save(source)
        try:
            with patch('core.note.get_position_manager') as mp, patch('core.note.QFileDialog.getOpenFileName', return_value=(source, '')):
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(995, temp_dir, manager=None)
                self.assertTrue(note.choose_background_image())
                self.assertTrue(note.background_image.startswith('images/background_995_'))
                self.assertTrue(note._has_background_image())
                self.assertEqual(note.control_opacity_slider.value(), 86)
                self.assertTrue(note.clear_background_btn.isEnabled())
                self.assertTrue(note.background_btn.text())
                note.change_control_opacity(64)
                self.assertEqual(note.control_opacity, 0.64)
                self.assertEqual(note.note_data['control_opacity'], 0.64)
                self.assertIn('rgba(', note.bold_btn.styleSheet())
                self.assertIn(', 163)', note.bold_btn.styleSheet())
                note.clear_background_image()
                self.assertEqual(note.background_image, '')
                self.assertFalse(note._has_background_image())
                self.assertFalse(note.clear_background_btn.isEnabled())
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_failed_background_replace_restores_same_named_managed_file(self):
        """A post-copy failure must not destroy the note's previous image."""
        from core.note import StickyNote

        temp_dir = tempfile.mkdtemp()
        source_dir = os.path.join(temp_dir, 'source')
        os.makedirs(source_dir)
        source = os.path.join(source_dir, 'same.png')
        source_image = QImage(12, 8, QImage.Format_RGB32)
        source_image.fill(QColor('#3366CC'))
        self.assertTrue(source_image.save(source))
        try:
            with patch('core.note.get_position_manager') as positions:
                positions.return_value.get_smart_position.return_value = QPoint(100, 100)
                positions.return_value.is_position_valid.return_value = True
                note = StickyNote(994, temp_dir, manager=None)

            images_dir = os.path.join(temp_dir, 'images')
            os.makedirs(images_dir, exist_ok=True)
            managed = os.path.join(images_dir, 'background_994_same.png')
            old_image = QImage(12, 8, QImage.Format_RGB32)
            old_image.fill(QColor('#CC6633'))
            self.assertTrue(old_image.save(managed))
            with open(managed, 'rb') as old_file:
                original_bytes = old_file.read()
            note.background_image = 'images/background_994_same.png'
            self.assertTrue(note._load_background_pixmap())

            with patch(
                'core.note.QFileDialog.getOpenFileName', return_value=(source, '')
            ), patch.object(
                note, '_load_background_pixmap', side_effect=[False, True]
            ), patch('core.note.QMessageBox.warning'):
                self.assertFalse(note.choose_background_image())

            with open(managed, 'rb') as restored_file:
                self.assertEqual(restored_file.read(), original_bytes)
            self.assertEqual(
                note.background_image, 'images/background_994_same.png'
            )
            self.assertEqual(
                [name for name in os.listdir(images_dir) if name.startswith('.')],
                [],
            )
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_tool_rail_reflows_pages_without_overlap_at_narrow_widths(self):
        """三页在窄窗中独立滚动，组与导航/页面之间不得互相覆盖。"""
        from core.note import StickyNote

        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(995, temp_dir, manager=None)

            page_specs = (
                (note.format_scroll, note.format_panel, note.format_tool_groups),
                (note.settings_scroll, note.settings_panel, note.settings_tool_groups),
                (note.action_scroll, note.action_panel, note.action_tool_groups),
            )
            note.show()
            for width in (240, 320, 400):
                with self.subTest(width=width):
                    note.resize(width, 300)
                    QApplication.processEvents()

                    nav_rect = note.tool_rail_nav.geometry()
                    stack_rect = note.tool_rail_stack.geometry()
                    self.assertLess(
                        nav_rect.right(), stack_rect.left(),
                        f'导航与页面重叠: width={width}',
                    )
                    self.assertEqual(
                        note.tool_rail_stack.geometry().height(),
                        note.format_scroll.height(),
                    )

                    for index, (scroll, panel, groups) in enumerate(page_specs):
                        with self.subTest(page=index):
                            note._show_tool_rail(index)
                            QApplication.processEvents()
                            self.assertTrue(scroll.isVisible())
                            for other_index, (other_scroll, _, _) in enumerate(page_specs):
                                if other_index != index:
                                    self.assertFalse(other_scroll.isVisible())

                            panel.layout().activate()
                            self.assertGreaterEqual(
                                panel.width(), panel.layout().sizeHint().width(),
                                f'内容面板宽度过小: width={width}, page={index}',
                            )
                            self.assertGreaterEqual(
                                panel.height(), panel.layout().sizeHint().height(),
                                f'内容面板高度过小: width={width}, page={index}',
                            )
                            for previous, current in zip(groups, groups[1:]):
                                self.assertLess(
                                    previous.geometry().right(),
                                    current.geometry().left(),
                                    f'工具组重叠: width={width}, page={index}',
                                )
                            for group in groups:
                                group_rect = group.rect()
                                for child_index in range(group.layout().count()):
                                    child = group.layout().itemAt(child_index).widget()
                                    if child is None:
                                        continue
                                    self.assertGreaterEqual(child.geometry().left(), group_rect.left())
                                    self.assertLessEqual(child.geometry().right(), group_rect.right())
                                    self.assertGreaterEqual(child.geometry().top(), group_rect.top())
                                    self.assertLessEqual(child.geometry().bottom(), group_rect.bottom())

                            scrollbar = scroll.horizontalScrollBar()
                            self.assertGreaterEqual(scrollbar.maximum(), 0)
                            self.assertGreaterEqual(
                                scrollbar.sizeHint().height(), 10,
                                f'滚动条命中高度过小: width={width}, page={index}',
                            )
                            scrollbar.setValue(scrollbar.maximum())
                            QApplication.processEvents()

            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_new_note_shows_all_action_buttons_and_common_settings_lead(self):
        from core.note import StickyNote
        from core.ui_preferences import DEFAULT_SETTINGS_TOOL_ORDER

        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(9941, temp_dir, manager=None)
            note.show()
            note._show_tool_rail(2)
            QApplication.processEvents()
            self.assertEqual(note.size(), note.recommended_initial_size())
            self.assertEqual(note.action_scroll.horizontalScrollBar().maximum(), 0)
            key_by_group = {
                group: key for key, group in note.settings_tool_group_map.items()
            }
            self.assertEqual(
                [key_by_group[group] for group in note.settings_tool_groups],
                list(DEFAULT_SETTINGS_TOOL_ORDER),
            )
            self.assertEqual(
                [group.objectName() for group in note.settings_tool_groups[:2]],
                ['settingsWindowOpacityGroup', 'settingsBehaviourGroup'],
            )
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_settings_tool_order_can_be_reconfigured_without_recreating_controls(self):
        from core.note import StickyNote

        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(9942, temp_dir, manager=None)
            original_controls = (
                note.transparency_slider, note.topmost_checkbox,
                note.format_checkbox, note.background_btn,
            )
            requested = [
                'background', 'window_opacity', 'behaviour',
                'control_opacity', 'background_colors',
            ]
            self.assertEqual(note.apply_settings_tool_order(requested), requested)
            self.assertEqual(
                [group.objectName() for group in note.settings_tool_groups],
                [
                    'settingsBackgroundGroup', 'settingsWindowOpacityGroup',
                    'settingsBehaviourGroup', 'settingsControlOpacityGroup',
                    'settingsColorGroup',
                ],
            )
            self.assertEqual(
                original_controls,
                (note.transparency_slider, note.topmost_checkbox,
                 note.format_checkbox, note.background_btn),
            )
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_theme_colors_drive_title_editor_and_controls(self):
        from core.note import StickyNote, _contrast_ratio
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                data = {
                    'title': '主题测试', 'content': '', 'plain_content': '',
                    'opacity': 0.9, 'always_on_top': True, 'theme': 'elegant_green.css',
                    'background_image': '', 'control_opacity': 1.0,
                }
                note = StickyNote(993, temp_dir, manager=None, preloaded_data=data)
                self.assertIn('#ccffcc', note.title_edit.styleSheet().lower())
                self.assertIn('#ccffcc', note.text_edit.styleSheet().lower())
                styles = note._current_theme_styles
                self.assertGreaterEqual(_contrast_ratio(styles['text'], styles['editor_bg']), 4.5)
                self.assertGreaterEqual(_contrast_ratio(styles['title_text'], styles['title_surface']), 4.5)
                self.assertGreaterEqual(_contrast_ratio(styles['control_text'], styles['control_surface']), 4.5)
                self.assertGreaterEqual(_contrast_ratio(styles['control_surface'], styles['canvas']), 3.0)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_all_preset_themes_keep_default_text_and_controls_readable(self):
        from core.note import StickyNote, _contrast_ratio
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(990, temp_dir, manager=None)
                styles_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'styles')
                for theme in sorted(name for name in os.listdir(styles_dir) if name.endswith('.css')):
                    with self.subTest(theme=theme):
                        note.set_theme(theme)
                        styles = note._current_theme_styles
                        self.assertGreaterEqual(
                            _contrast_ratio(styles['text'], styles['editor_bg']), 4.5
                        )
                        self.assertGreaterEqual(
                            _contrast_ratio(styles['title_text'], styles['title_surface']), 4.5
                        )
                        self.assertGreaterEqual(
                            _contrast_ratio(styles['control_text'], styles['control_surface']), 4.5
                        )
                        self.assertGreaterEqual(
                            _contrast_ratio(styles['control_text'], styles['control_hover']), 4.5
                        )
                        for surface_name in ('rail_surface', 'rail_hover', 'rail_checked'):
                            self.assertGreaterEqual(
                                _contrast_ratio(styles['rail_text'], styles[surface_name]), 4.5
                            )
                        self.assertGreaterEqual(
                            _contrast_ratio(styles['control_surface'], styles['canvas']), 3.0
                        )
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_legacy_font_color_mode_migration(self):
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                base = {
                    'title': '迁移', 'content': '', 'plain_content': '',
                    'opacity': 0.9, 'always_on_top': True, 'theme': 'soft_yellow.css',
                }
                theme_note = StickyNote(
                    989, temp_dir, manager=None,
                    preloaded_data={**base, 'font_color': '#000000'},
                )
                self.assertEqual(theme_note.font_color_mode, 'theme')
                theme_note.is_deleted = True
                theme_note.close()

                manual_note = StickyNote(
                    988, temp_dir, manager=None,
                    preloaded_data={**base, 'font_color': '#7a2244'},
                )
                self.assertEqual(manual_note.font_color_mode, 'manual')
                self.assertEqual(manual_note._current_theme_styles['text'], '#7a2244')
                manual_note.is_deleted = True
                manual_note.close()

                corrupt_note = StickyNote(
                    985, temp_dir, manager=None,
                    preloaded_data={
                        **base, 'theme': 'dark_modern.css',
                        'font_color': 'not-a-color', 'font_color_mode': 'manual',
                    },
                )
                self.assertEqual(corrupt_note.font_color_mode, 'theme')
                self.assertNotEqual(corrupt_note._current_theme_styles['text'], '#000000')
                corrupt_note.is_deleted = True
                corrupt_note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_explicit_black_font_color_is_manual_and_title_focus_is_safe(self):
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(987, temp_dir, manager=None)
                with patch.object(note, '_get_focused_editor', return_value=note.title_edit), \
                     patch('core.note.QColorDialog.getColor', return_value=QColor('#000000')):
                    self.assertTrue(note.choose_font_color())
                self.assertEqual(note.font_color_mode, 'manual')
                self.assertEqual(note.font_color, '#000000')
                self.assertEqual(note.note_data['font_color_mode'], 'manual')
                with patch('core.note.QColorDialog.getColor', return_value=QColor()):
                    self.assertFalse(note.choose_font_color())
                self.assertTrue(note.color_btn.isChecked())
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_selected_body_font_color_is_inline_only_and_title_stays_theme(self):
        """正文选区改色只能写入该选区，不能污染正文默认色或标题。"""
        from core.note import StickyNote

        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(
                    984, temp_dir, manager=None,
                    preloaded_data={
                        'title': '标题默认色', 'content': '', 'plain_content': '',
                        'opacity': 0.9, 'always_on_top': True,
                        'theme': 'soft_yellow.css',
                    },
                )

            note.text_edit.setPlainText('正文甲 正文乙')
            note.text_edit.setFocus()
            cursor = note.text_edit.textCursor()
            cursor.setPosition(0)
            cursor.setPosition(3, QTextCursor.KeepAnchor)
            note.text_edit.setTextCursor(cursor)

            original_font_color = note.font_color
            original_font_mode = note.font_color_mode
            original_title_style = note.title_edit.styleSheet()
            original_title_token = note._current_theme_styles['title_text']
            with patch('core.note.QColorDialog.getColor', return_value=QColor('#ff0000')):
                self.assertTrue(note.choose_font_color())

            def color_at(position):
                probe = note.text_edit.textCursor()
                probe.setPosition(position)
                probe.setPosition(position + 1, QTextCursor.KeepAnchor)
                color = probe.charFormat().foreground().color()
                return color.name().lower() if color.isValid() else ''

            self.assertEqual(color_at(0), '#ff0000')
            self.assertNotEqual(color_at(4), '#ff0000')
            self.assertEqual(note.font_color, original_font_color)
            self.assertEqual(note.font_color_mode, original_font_mode)
            self.assertEqual(note.note_data['font_color_mode'], original_font_mode)
            self.assertEqual(note.title_edit.styleSheet(), original_title_style)
            self.assertEqual(note._current_theme_styles['title_text'], original_title_token)
            self.assertNotIn('#ff0000', note.title_edit.styleSheet().lower())
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_body_font_color_without_selection_changes_insertion_format_not_title(self):
        """无选区时更新正文后续输入格式，标题仍保留主题颜色。"""
        from core.note import StickyNote

        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(
                    983, temp_dir, manager=None,
                    preloaded_data={
                        'title': '标题保持主题色', 'content': '正文',
                        'plain_content': '正文', 'opacity': 0.9,
                        'always_on_top': True, 'theme': 'soft_yellow.css',
                    },
                )

            note.text_edit.setFocus()
            cursor = note.text_edit.textCursor()
            cursor.setPosition(len(note.text_edit.toPlainText()))
            note.text_edit.setTextCursor(cursor)
            with patch('core.note.QColorDialog.getColor', return_value=QColor('#123456')):
                self.assertTrue(note.choose_font_color())

            self.assertEqual(note.font_color, '#123456')
            self.assertEqual(note.font_color_mode, 'manual')
            self.assertEqual(note.note_data['font_color_mode'], 'manual')
            self.assertEqual(
                note.text_edit.currentCharFormat().foreground().color().name().lower(),
                '#123456',
            )
            self.assertNotIn('#123456', note.title_edit.styleSheet().lower())
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_background_color_overrides_do_not_replace_manual_or_inline_text(self):
        from core.note import StickyNote, _contrast_ratio
        temp_dir = tempfile.mkdtemp()
        background = os.path.join(temp_dir, 'background.png')
        image = QImage(32, 32, QImage.Format_RGB32)
        image.fill(QColor('#eeeeee'))
        image.save(background)
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                data = {
                    'title': '背景颜色',
                    'content': '<p><span style=" color:#ff0000;">行内红色</span></p>',
                    'plain_content': '行内红色', 'opacity': 0.9,
                    'always_on_top': True, 'theme': 'soft_yellow.css',
                    'background_image': background, 'control_opacity': 0.86,
                    'font_color': '#123456', 'font_color_mode': 'manual',
                }
                note = StickyNote(986, temp_dir, manager=None, preloaded_data=data)
                before_html = note.text_edit.toHtml().lower()
                with patch('core.note.QColorDialog.getColor', return_value=QColor('#fafafa')):
                    self.assertTrue(note.choose_background_text_color())
                with patch('core.note.QColorDialog.getColor', return_value=QColor('#223344')):
                    self.assertTrue(note.choose_background_control_color())
                styles = note._current_theme_styles
                self.assertEqual(note.background_text_color, '#fafafa')
                self.assertEqual(note.background_control_color, '#223344')
                self.assertEqual(styles['text'], '#123456')
                self.assertEqual(note.font_color, '#123456')
                self.assertEqual(note.font_color_mode, 'manual')
                self.assertEqual(note.note_data['background_text_color'], '#fafafa')
                self.assertEqual(note.note_data['background_control_color'], '#223344')
                self.assertGreaterEqual(
                    _contrast_ratio(styles['control_text'], styles['control_surface']), 4.5
                )
                note.font_color_mode = 'theme'
                note.apply_theme()
                self.assertEqual(note._current_theme_styles['text'], '#fafafa')
                note.font_color_mode = 'manual'
                note.apply_theme()
                self.assertIn('#ff0000', before_html)
                self.assertIn('#ff0000', note.text_edit.toHtml().lower())
                self.assertTrue(note.reset_background_colors())
                self.assertEqual(note.background_text_color, '')
                self.assertEqual(note.background_control_color, '')
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_background_auto_text_uses_sampled_image_contrast(self):
        from core.note import StickyNote, _contrast_ratio, _mix_colors
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                for index, image_color in enumerate(('#050505', '#fafafa')):
                    path = os.path.join(temp_dir, f'background_{index}.png')
                    image = QImage(32, 32, QImage.Format_RGB32)
                    image.fill(QColor(image_color))
                    image.save(path)
                    data = {
                        'title': '自动对比', 'content': '', 'plain_content': '',
                        'opacity': 1.0, 'always_on_top': True, 'theme': 'soft_yellow.css',
                        'background_image': path, 'control_opacity': 0.86,
                        'font_color': '#000000', 'font_color_mode': 'theme',
                    }
                    note = StickyNote(980 + index, temp_dir, manager=None, preloaded_data=data)
                    styles = note._current_theme_styles
                    reference = note._background_reference_color().name()
                    effective_editor = _mix_colors(
                        reference, styles['editor_bg'], note.control_opacity
                    )
                    self.assertGreaterEqual(
                        _contrast_ratio(styles['text'], effective_editor), 4.5
                    )
                    note.is_deleted = True
                    note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_image_background_chrome_uses_composited_contrast_for_every_theme(self):
        from core.note import StickyNote, _contrast_ratio
        temp_dir = tempfile.mkdtemp()
        background = os.path.join(temp_dir, 'bright_background.png')
        image = QImage(64, 64, QImage.Format_RGB32)
        image.fill(QColor('#f7f4ea'))
        image.save(background)
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                data = {
                    'title': '底栏对比度', 'content': '', 'plain_content': '',
                    'opacity': 1.0, 'always_on_top': True,
                    'theme': 'soft_yellow.css', 'background_image': background,
                    'control_opacity': 0.86, 'font_color_mode': 'theme',
                }
                note = StickyNote(979, temp_dir, manager=None, preloaded_data=data)
                styles_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'styles')
                for theme in sorted(name for name in os.listdir(styles_dir) if name.endswith('.css')):
                    with self.subTest(theme=theme):
                        note.set_theme(theme)
                        styles = note._current_theme_styles
                        for surface_name in (
                                'effective_control_surface',
                                'effective_control_hover',
                                'effective_accent_surface'):
                            self.assertGreaterEqual(
                                _contrast_ratio(styles['control_text'], styles[surface_name]),
                                4.5,
                            )
                        for surface_name in ('rail_surface', 'rail_hover', 'rail_checked'):
                            self.assertGreaterEqual(
                                _contrast_ratio(styles['rail_text'], styles[surface_name]),
                                4.5,
                            )
                        self.assertGreaterEqual(
                            _contrast_ratio(
                                styles['panel_text'], styles['effective_panel_surface']
                            ),
                            4.5,
                        )
                        rail_style = note.tool_rail_buttons[0].styleSheet().lower()
                        self.assertIn(
                            f"background: {styles['rail_surface'].lower()}", rail_style
                        )
                        self.assertNotIn('background: transparent; color:', rail_style)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_corrupt_control_opacity_uses_safe_default(self):
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                data = {
                    'title': '容错测试', 'content': '', 'plain_content': '',
                    'opacity': 0.9, 'always_on_top': True, 'theme': 'soft_yellow.css',
                    'background_image': '', 'control_opacity': 'broken',
                }
                note = StickyNote(992, temp_dir, manager=None, preloaded_data=data)
                self.assertEqual(note.control_opacity, 1.0)
                self.assertEqual(note.control_opacity_slider.value(), 100)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_high_contrast_keeps_bright_keyboard_focus(self):
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                data = {
                    'title': '高对比测试', 'content': '', 'plain_content': '',
                    'opacity': 1.0, 'always_on_top': True, 'theme': 'high_contrast.css',
                    'background_image': '', 'control_opacity': 1.0,
                }
                note = StickyNote(991, temp_dir, manager=None, preloaded_data=data)
                self.assertIn('#ffff00', note.title_edit.styleSheet().lower())
                self.assertIn('#ffff00', note.tool_rail_buttons[0].styleSheet().lower())
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_invalid_background_keeps_previous_state_and_external_not_deleted(self):
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        source = os.path.join(temp_dir, 'valid.png')
        invalid = os.path.join(temp_dir, 'invalid.png')
        QImage(8, 8, QImage.Format_RGB32).save(source)
        with open(invalid, 'wb') as fh:
            fh.write(b'not an image')
        try:
            with patch('core.note.get_position_manager') as mp, patch('core.note.QFileDialog.getOpenFileName', return_value=(source, '')):
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(994, temp_dir, manager=None)
                self.assertTrue(note.choose_background_image())
                old = note.background_image
                with patch('core.note.QFileDialog.getOpenFileName', return_value=(invalid, '')), \
                     patch('core.note.QMessageBox.warning'):
                    self.assertFalse(note.choose_background_image())
                self.assertEqual(note.background_image, old)
                external = os.path.join(temp_dir, 'external.png')
                QImage(4, 4, QImage.Format_RGB32).save(external)
                note.background_image = external
                note._load_background_pixmap()
                note.clear_background_image()
                self.assertTrue(os.path.exists(external))

                # Even a legacy absolute path inside the managed-looking
                # images folder is external unless the stored value is relative.
                images_dir = os.path.join(temp_dir, 'images')
                os.makedirs(images_dir, exist_ok=True)
                absolute_managed_lookalike = os.path.join(
                    images_dir, 'background_994_external.png'
                )
                QImage(4, 4, QImage.Format_RGB32).save(absolute_managed_lookalike)
                note.background_image = absolute_managed_lookalike
                note._load_background_pixmap()
                note.clear_background_image()
                self.assertTrue(os.path.exists(absolute_managed_lookalike))
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_modern_tool_rail_preserves_all_actions(self):
        """工具轨道只切换呈现，不能删减控件、信号或窄窗可用性。"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(996, temp_dir, manager=None)
                action_names = [
                    'decrease_font_btn', 'increase_font_btn', 'bold_btn',
                    'italic_btn', 'color_btn', 'underline_btn',
                    'strikethrough_btn', 'superscript_btn', 'subscript_btn',
                    'align_left_btn', 'align_center_btn', 'align_right_btn',
                    'ordered_list_btn', 'unordered_list_btn', 'highlight_btn',
                    'clear_highlight_btn', 'undo_btn', 'redo_btn', 'tag_btn',
                    'reminder_btn', 'lock_btn', 'link_btn', 'image_btn',
                    'md_toggle_btn', 'backlink_btn', 'delete_btn', 'help_btn',
                    'hide_btn', 'background_btn', 'clear_background_btn',
                    'background_text_color_btn', 'background_control_color_btn',
                    'reset_background_colors_btn',
                ]
                controls = [getattr(note, name) for name in action_names]
                receiver_counts = [control.receivers(control.clicked) for control in controls]

                self.assertEqual(note.minimumWidth(), 240)
                self.assertEqual(note.minimumHeight(), 240)
                self.assertEqual(note.tool_rail_stack.count(), 3)
                self.assertEqual(note.tool_rail_stack.currentWidget(), note.action_scroll)
                self.assertTrue(all(not control.icon().isNull() for control in controls))
                self.assertTrue(all(control.accessibleName() for control in controls))
                self.assertTrue(all(count > 0 for count in receiver_counts))
                self.assertEqual(len(note.format_tool_groups), 8)
                self.assertEqual(len(note.settings_tool_groups), 5)
                self.assertEqual(len(note.action_tool_groups), 5)
                all_groups = (
                    note.format_tool_groups + note.settings_tool_groups +
                    note.action_tool_groups + [note.tool_rail_nav]
                )
                self.assertTrue(all(group.property('toolGroup') for group in all_groups))
                self.assertTrue(all(group.accessibleName() for group in all_groups))
                self.assertIn('QFrame[toolGroup="true"]', note.control_panel.styleSheet())
                self.assertTrue(all(button.size() == button.minimumSize()
                                    for button in note.tool_rail_buttons))
                self.assertTrue(all(button.width() == 36 and button.height() == 36
                                    for button in note.tool_rail_buttons))

                format_buttons = controls[:16]
                self.assertTrue(all(button.width() >= 34 and button.height() >= 32
                                    for button in format_buttons))
                self.assertGreaterEqual(note.hide_btn.width(), 76)
                self.assertGreaterEqual(note.delete_btn.width(), 76)

                note._show_tool_rail(0)
                self.assertEqual(note.tool_rail_stack.currentWidget(), note.format_scroll)
                note._show_tool_rail(1)
                self.assertEqual(note.tool_rail_stack.currentWidget(), note.settings_scroll)
                note._show_tool_rail(2)
                self.assertEqual(note.tool_rail_stack.currentWidget(), note.action_scroll)
                self.assertEqual(
                    receiver_counts,
                    [control.receivers(control.clicked) for control in controls],
                )
                note.resize(240, 240)
                self.assertEqual(note.size().width(), 240)
                self.assertEqual(note.size().height(), 240)
                note.show()
                QApplication.processEvents()
                page_checks = (
                    (0, note.format_scroll, note.clear_highlight_btn),
                    (1, note.settings_scroll, note.reset_background_colors_btn),
                    (2, note.action_scroll, note.delete_btn),
                )
                for index, scroll, last_control in page_checks:
                    with self.subTest(tool_page=index):
                        note._show_tool_rail(index)
                        QApplication.processEvents()
                        scrollbar = scroll.horizontalScrollBar()
                        self.assertGreater(scrollbar.maximum(), 0)
                        scrollbar.setValue(scrollbar.maximum())
                        QApplication.processEvents()
                        top_left = last_control.mapTo(scroll.viewport(), QPoint(0, 0))
                        last_rect = QRect(top_left, last_control.size())
                        self.assertTrue(last_rect.intersects(scroll.viewport().rect()))

                for group in all_groups:
                    group_layout = group.layout()
                    group_controls = [
                        group_layout.itemAt(i).widget()
                        for i in range(group_layout.count())
                        if group_layout.itemAt(i).widget() is not None
                    ]
                    for previous, current in zip(group_controls, group_controls[1:]):
                        self.assertLess(previous.geometry().right(), current.geometry().left())
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)


class TestStickyNotePathSecurity(unittest.TestCase):
    """StickyNote — 路径穿越防护"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_valid_note_file_accepted(self):
        """合法路径应被接受"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(888, temp_dir, manager=None)
                self.assertIsNotNone(note)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_path_traversal_blocked(self):
        """路径穿越应抛出 ValueError"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            # 创建恶意 note_id 使路径指向外部
            # 使用 os.path.realpath 验证机制
            with self.assertRaises(ValueError):
                # 使用 '../../../' 构造路径穿越（必须真正逃逸出 notes_dir）
                StickyNote('../../../malicious', temp_dir, manager=None)
        finally:
            shutil.rmtree(temp_dir)


class TestStickyNoteUpdateButtons(unittest.TestCase):
    """StickyNote — _update_undo_redo_buttons 方法"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_buttons_update_on_state_change(self):
        """撤销/重做状态变化时应更新按钮"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(777, temp_dir, manager=None)
                # 模拟有可撤销状态
                note._update_undo_redo_buttons(True, False)
                self.assertTrue(note.undo_btn.isEnabled())
                self.assertFalse(note.redo_btn.isEnabled())
                # 模拟都可操作
                note._update_undo_redo_buttons(True, True)
                self.assertTrue(note.undo_btn.isEnabled())
                self.assertTrue(note.redo_btn.isEnabled())
                # 模拟都不可操作
                note._update_undo_redo_buttons(False, False)
                self.assertFalse(note.undo_btn.isEnabled())
                self.assertFalse(note.redo_btn.isEnabled())
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)


class TestStickyNoteScreenGeometry(unittest.TestCase):
    """StickyNote — 屏幕几何缓存"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_cache_attributes_exist(self):
        """应存在屏幕几何缓存属性"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(776, temp_dir, manager=None)
                self.assertTrue(hasattr(note, '_screen_geo_cache'))
                self.assertTrue(hasattr(note, '_screen_geo_cache_time'))
                self.assertIsNone(note._screen_geo_cache)
                self.assertEqual(note._screen_geo_cache_time, 0)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_get_screen_geometry_returns_valid(self):
        """_get_screen_geometry 应返回有效值"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(775, temp_dir, manager=None)
                geo = note._get_screen_geometry()
                self.assertIsNotNone(geo)
                self.assertGreater(geo.width(), 0)
                self.assertGreater(geo.height(), 0)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)


class TestStickyNoteBorderPen(unittest.TestCase):
    """StickyNote — paintEvent 渲染缓存"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def test_border_pen_cached(self):
        """边框画笔应被缓存为实例属性"""
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(774, temp_dir, manager=None)
                self.assertTrue(hasattr(note, '_border_pen'))
                from PyQt5.QtGui import QPen
                self.assertIsInstance(note._border_pen, QPen)
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)


class TestStickyNoteRoundedWindow(unittest.TestCase):
    """Rounded top-level composition and resize safety."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def _make_note(self, note_id, temp_dir):
        from core.note import StickyNote
        with patch('core.note.get_position_manager') as mp:
            mp.return_value.get_smart_position.return_value = QPoint(100, 100)
            mp.return_value.is_position_valid.return_value = True
            return StickyNote(note_id, temp_dir, manager=None)

    def test_mask_excludes_rounded_corners(self):
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._make_note(773, temp_dir)
            note._update_window_shape()
            mask = note.mask()
            if mask.isEmpty():
                self.skipTest('当前 Qt 平台不支持顶层窗口 mask')
            center = QPoint(note.width() // 2, note.height() // 2)
            self.assertTrue(mask.contains(center))
            self.assertFalse(mask.contains(QPoint(0, 0)))
            self.assertFalse(mask.contains(QPoint(note.width() - 1, 0)))
            self.assertFalse(mask.contains(QPoint(0, note.height() - 1)))
            self.assertFalse(mask.contains(QPoint(note.width() - 1, note.height() - 1)))
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_rendered_border_does_not_repaint_transparent_corners(self):
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._make_note(7721, temp_dir)
            note.resize(400, 300)
            note.show()
            self.app.processEvents()
            image = note.grab().toImage()
            for point in (QPoint(0, 0), QPoint(1, 1), QPoint(3, 3)):
                with self.subTest(point=(point.x(), point.y())):
                    self.assertEqual(image.pixelColor(point).alpha(), 0)
            self.assertGreater(image.pixelColor(QPoint(14, 14)).alpha(), 0)
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_mask_rebuilt_after_resize(self):
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._make_note(772, temp_dir)
            note.resize(320, 280)
            self.app.processEvents()
            mask = note.mask()
            if mask.isEmpty():
                self.skipTest('当前 Qt 平台不支持顶层窗口 mask')
            self.assertGreaterEqual(mask.boundingRect().width(), 300)
            self.assertGreaterEqual(mask.boundingRect().height(), 260)
            self.assertTrue(mask.contains(QPoint(160, 140)))
            self.assertFalse(mask.contains(QPoint(0, 0)))
            note.resize(240, 240)
            self.app.processEvents()
            resized_mask = note.mask()
            self.assertTrue(resized_mask.contains(QPoint(120, 120)))
            self.assertFalse(resized_mask.contains(QPoint(0, 0)))
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_interactive_resize_honours_widget_minimum(self):
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._make_note(771, temp_dir)
            note.setGeometry(100, 100, 400, 300)
            note.initial_geometry = note.geometry()
            note.drag_pos = note.geometry().bottomRight()
            note.resize_dir = 'bottom_right'
            note.resizing = True
            note.perform_resize(QPoint(-500, -500))
            self.assertGreaterEqual(note.width(), note.minimumWidth())
            self.assertGreaterEqual(note.height(), note.minimumHeight())
            self.assertGreaterEqual(note.width(), 240)
            self.assertGreaterEqual(note.height(), 240)
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_dwm_backdrop_is_safe_fallback_offscreen(self):
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            note = self._make_note(770, temp_dir)
            with patch('core.note.sys.platform', 'linux'):
                self.assertFalse(note._try_enable_system_backdrop())
            note.is_deleted = True
            note.close()
        finally:
            shutil.rmtree(temp_dir)

    def test_shape_event_lookup_ignores_missing_qt_enums(self):
        from types import SimpleNamespace
        import core.note as note_module

        with patch.object(note_module, 'QEvent', SimpleNamespace(DevicePixelRatioChange=123)):
            self.assertEqual(note_module._shape_refresh_event_types(), (123,))
        with patch.object(note_module, 'QEvent', SimpleNamespace()):
            self.assertEqual(note_module._shape_refresh_event_types(), ())

    def test_background_image_keeps_rounded_mask_and_paint_cache(self):
        temp_dir = tempfile.mkdtemp()
        source = os.path.join(temp_dir, 'rounded-source.png')
        QImage(24, 16, QImage.Format_RGB32).save(source)
        try:
            with patch('core.note.QFileDialog.getOpenFileName', return_value=(source, '')):
                note = self._make_note(769, temp_dir)
                self.assertTrue(note.choose_background_image())
                note.resize(300, 260)
                note.show()
                self.app.processEvents()
                note.grab()
                self.assertFalse(note._background_pixmap.isNull())
                self.assertEqual(note._background_scaled_size, note.rect().size())
                mask = note.mask()
                if not mask.isEmpty():
                    self.assertFalse(mask.contains(QPoint(0, 0)))
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)


if __name__ == '__main__':
    unittest.main()

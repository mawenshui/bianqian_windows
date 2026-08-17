# -*- coding: utf-8 -*-
"""设置中心的主题、布局、可访问性与交互回归测试。"""

import os
import unittest

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import (
    QApplication, QLabel, QPushButton, QScrollArea, QComboBox, QSpinBox,
    QCheckBox, QLineEdit,
)

from core import get_styles_dir
from core.ui_preferences import (
    DEFAULT_SETTINGS_TOOL_ORDER, SETTINGS_TOOL_LABELS,
)
from core.settings import (
    SettingsDialog, _UniformFontDelegate, _UniformFontComboBox,
    _contrast_ratio, _settings_tokens,
)
from features.secret_storage import protect_secret, reveal_secret


class _FakeConfig:
    def __init__(self):
        self.values = {
            'sync.enabled': False,
            'sync.provider': 'webdav',
            'sync.auto_sync': False,
            'sync.sync_interval_minutes': 30,
            'plugins.enabled': True,
        }

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value, auto_save=True):
        self.values[key] = value


class _FakePluginRegistry:
    def list_plugins(self):
        return []


class _FakeManager:
    def __init__(self):
        self.settings = {'auto_check_update': True}
        self.config = _FakeConfig()
        self.plugin_registry = _FakePluginRegistry()
        self.current_theme = 'soft_yellow.css'
        self.theme_apply_count = 0
        self.font_apply_count = 0
        self.saved_settings_count = 0
        self.update_checks = []
        self.cancelled = False
        self.sync_setup_count = 0
        self.tool_order_apply_count = 0
        self.settings_tool_order = list(DEFAULT_SETTINGS_TOOL_ORDER)
        self.default_font = {
            'family': 'Microsoft YaHei', 'size': 12,
            'bold': False, 'italic': False,
        }

    def get_available_themes(self):
        return {
            '柔和黄色': 'soft_yellow.css',
            '现代暗黑': 'dark_modern.css',
            '高对比度': 'high_contrast.css',
        }

    def get_default_theme_css(self):
        return self.current_theme

    def get_theme_name_by_css(self, css_filename):
        for name, filename in self.get_available_themes().items():
            if filename == css_filename:
                return name
        return None

    def set_default_theme(self, css_filename):
        self.current_theme = css_filename

    def apply_theme_to_all_notes(self):
        self.theme_apply_count += 1

    def get_default_font(self):
        return dict(self.default_font)

    def set_default_font(self, font_settings):
        self.default_font = dict(font_settings)

    def apply_font_to_all_notes(self):
        self.font_apply_count += 1

    def save_settings(self):
        self.saved_settings_count += 1

    def check_for_updates(self, **kwargs):
        self.update_checks.append(kwargs)

    def cancel_update_check(self):
        self.cancelled = True

    def setup_sync_engine(self):
        self.sync_setup_count += 1

    def get_settings_tool_order(self):
        return list(self.settings_tool_order)

    def set_settings_tool_order(self, order):
        self.settings_tool_order = list(order)
        self.tool_order_apply_count += 1
        self.config.set('ui.settings_tool_order', list(order))
        return list(order)


class TestSettingsDialogUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.manager = _FakeManager()
        self.dialog = SettingsDialog(self.manager)
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        self.dialog.close()
        self.dialog.deleteLater()
        self.app.processEvents()

    def test_resizable_product_shell_and_seven_pages(self):
        self.assertEqual(self.dialog.objectName(), 'settingsDialog')
        self.assertGreaterEqual(self.dialog.width(), 760)
        self.assertGreaterEqual(self.dialog.height(), 580)
        self.assertLess(self.dialog.minimumWidth(), self.dialog.maximumWidth())
        self.assertLess(self.dialog.minimumHeight(), self.dialog.maximumHeight())
        self.assertEqual(self.dialog.tab_widget.count(), 7)
        self.assertEqual(
            [self.dialog.tab_widget.tabText(i) for i in range(7)],
            ['主题', '字体', '更新', '安全', '云同步', '插件', '快捷键'],
        )
        title = self.dialog.findChild(QLabel, 'settingsTitle')
        self.assertIsNotNone(title)
        self.assertEqual(title.font().pixelSize(), 22)
        header_icon = self.dialog.findChild(QLabel, 'settingsHeaderIcon')
        self.assertIsNotNone(header_icon)
        self.assertFalse(header_icon.pixmap().isNull())
        self.assertEqual(header_icon.focusPolicy(), Qt.NoFocus)

    def test_tabs_have_clear_vector_icons_and_accessible_names(self):
        self.assertEqual(self.dialog.tab_widget.accessibleName(), '设置分类')
        for index in range(self.dialog.tab_widget.count()):
            page = self.dialog.tab_widget.widget(index)
            self.assertFalse(self.dialog.tab_widget.tabIcon(index).isNull())
            self.assertTrue(page.accessibleName().endswith('设置') or page.accessibleName() == '云同步设置')
            self.assertTrue(bool(page.property('settingsIconKind')))
        self.assertLessEqual(
            self.dialog.tab_widget.tabBar().sizeHint().width(),
            self.dialog.tab_widget.width(),
        )
        style = self.dialog.styleSheet()
        self.assertIn('margin: 6px 3px 7px 3px', style)
        self.assertIn('border: 2px solid', style)

    def test_keyboard_navigation_changes_active_tab(self):
        bar = self.dialog.tab_widget.tabBar()
        self.dialog.tab_widget.setCurrentIndex(0)
        bar.setFocus()
        QTest.keyClick(bar, Qt.Key_Right)
        self.app.processEvents()
        self.assertEqual(self.dialog.tab_widget.currentIndex(), 1)
        QTest.keyClick(bar, Qt.Key_Left)
        self.assertEqual(self.dialog.tab_widget.currentIndex(), 0)

    def test_primary_controls_are_named_and_keyboard_reachable(self):
        names = (
            'theme_combo', 'font_family_combo', 'font_size_spinbox',
            'font_bold_checkbox', 'font_italic_checkbox', 'reset_font_btn',
            'auto_update_checkbox', 'check_update_btn', 'cancel_check_btn',
            'master_pwd_checkbox', 'set_master_pwd_btn', 'sync_enabled_cb',
            'sync_provider_combo', 'webdav_url', 'webdav_user', 'webdav_pwd',
            'webdav_path', 'save_webdav_btn', 'auto_sync_cb',
            'sync_interval_spin', 'plugins_enabled_cb', 'save_shortcuts_btn',
        )
        for name in names:
            control = getattr(self.dialog, name)
            self.assertTrue(control.accessibleName(), name)
            self.assertNotEqual(control.focusPolicy(), Qt.NoFocus, name)

    def test_theme_change_updates_notes_preview_and_dialog_chrome(self):
        self.dialog.theme_combo.setCurrentText('现代暗黑')
        self.app.processEvents()
        self.assertEqual(self.manager.current_theme, 'dark_modern.css')
        self.assertEqual(self.manager.theme_apply_count, 1)
        self.assertTrue(self.dialog._settings_theme_tokens['dark'])
        self.assertIn('QDialog#settingsDialog', self.dialog.styleSheet())
        self.assertIn('QFrame#themePreview', self.dialog.preview_note.styleSheet())
        self.assertFalse(self.dialog.preview_note.grab().isNull())

    def test_theme_preview_footer_is_not_clipped(self):
        self.dialog.tab_widget.setCurrentIndex(0)
        self.dialog.resize(self.dialog.minimumSize())
        self.app.processEvents()
        preview_rect = self.dialog.preview_note.rect()
        for chip in self.dialog.preview_footer_chips:
            top_left = chip.mapTo(self.dialog.preview_note, QPoint(0, 0))
            self.assertTrue(preview_rect.contains(top_left), chip.text())
            self.assertTrue(
                preview_rect.contains(top_left + QPoint(chip.width() - 1, chip.height() - 1)),
                chip.text(),
            )

    def test_theme_page_reorders_common_tools_with_live_preview(self):
        order_list = self.dialog.settings_tool_order_list
        keys = [
            order_list.item(index).data(Qt.UserRole)
            for index in range(order_list.count())
        ]
        self.assertEqual(keys, list(DEFAULT_SETTINGS_TOOL_ORDER))
        self.assertEqual(
            [order_list.item(index).text() for index in range(order_list.count())],
            [SETTINGS_TOOL_LABELS[key] for key in DEFAULT_SETTINGS_TOOL_ORDER],
        )
        preview_labels = [
            label for label in self.dialog.tool_order_preview.findChildren(QLabel)
            if label.property('previewChip')
        ]
        self.assertEqual(len(preview_labels), len(DEFAULT_SETTINGS_TOOL_ORDER))

        order_list.setCurrentRow(0)
        self.dialog.tool_order_down_btn.click()
        self.app.processEvents()
        self.assertEqual(
            self.manager.settings_tool_order[:2],
            ['behaviour', 'window_opacity'],
        )
        self.assertGreater(self.manager.tool_order_apply_count, 0)
        preview_labels = [
            label.text() for label in self.dialog.tool_order_preview.findChildren(QLabel)
            if label.property('previewChip')
        ]
        self.assertEqual(
            preview_labels[:2],
            [SETTINGS_TOOL_LABELS['behaviour'], SETTINGS_TOOL_LABELS['window_opacity']],
        )

        self.dialog.tool_order_reset_btn.click()
        self.assertEqual(
            self.manager.settings_tool_order,
            list(DEFAULT_SETTINGS_TOOL_ORDER),
        )

    def test_theme_page_scroll_keeps_order_editor_and_preview_reachable(self):
        self.dialog.resize(self.dialog.minimumSize())
        self.dialog.tab_widget.setCurrentIndex(0)
        self.app.processEvents()
        scrollbar = self.dialog.theme_scroll.verticalScrollBar()
        self.assertGreater(scrollbar.maximum(), 0)
        scrollbar.setValue(scrollbar.maximum())
        self.app.processEvents()
        preview_pos = self.dialog.preview_note.mapTo(
            self.dialog.theme_scroll.viewport(), QPoint(0, 0)
        )
        preview_rect = QRect(preview_pos, self.dialog.preview_note.size())
        self.assertTrue(
            preview_rect.intersects(self.dialog.theme_scroll.viewport().rect())
        )

    def test_high_contrast_theme_keeps_bright_focus_and_active_colour(self):
        self.dialog.theme_combo.setCurrentText('高对比度')
        self.app.processEvents()
        tokens = self.dialog._settings_theme_tokens
        self.assertTrue(tokens['high_contrast'])
        self.assertEqual(tokens['accent'].upper(), '#FFFF00')
        self.assertEqual(tokens['border'].upper(), '#FFFF00')

    def test_font_changes_and_reset_keep_existing_persistence(self):
        before = self.manager.font_apply_count
        self.dialog.font_size_spinbox.setValue(18)
        self.dialog.font_bold_checkbox.setChecked(True)
        self.app.processEvents()
        self.assertEqual(self.manager.default_font['size'], 18)
        self.assertTrue(self.manager.default_font['bold'])
        self.assertGreater(self.manager.font_apply_count, before)
        self.dialog.reset_font_settings()
        self.assertEqual(self.dialog.font_size_spinbox.value(), 12)
        self.assertFalse(self.dialog.font_bold_checkbox.isChecked())
        self.assertFalse(self.dialog.font_italic_checkbox.isChecked())

    def test_font_picker_uses_uniform_rows_and_bounded_popup(self):
        picker = self.dialog.font_family_combo
        self.assertIsInstance(picker, _UniformFontComboBox)
        self.assertIsInstance(picker.itemDelegate(), _UniformFontDelegate)
        self.assertTrue(picker.view().uniformItemSizes())
        self.assertEqual(picker.view().horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
        first = picker.model().index(0, 0)
        last = picker.model().index(max(0, picker.count() - 1), 0)
        self.assertEqual(
            picker.itemDelegate().sizeHint(picker.view().viewOptions(), first).height(),
            picker.itemDelegate().sizeHint(picker.view().viewOptions(), last).height(),
        )
        picker.showPopup()
        self.app.processEvents()
        self.assertLessEqual(picker.view().window().width(), self.dialog.width())
        picker.hidePopup()

    def test_settings_chrome_uses_one_ui_font_and_explicit_combo_arrow(self):
        reference = self.dialog.font()
        for control in (
            self.dialog.theme_combo, self.dialog.font_size_spinbox,
            self.dialog.reset_font_btn, self.dialog.auto_update_checkbox,
        ):
            self.assertEqual(control.font().family(), reference.family())
            self.assertEqual(control.font().pixelSize(), 14)
        style = self.dialog.styleSheet()
        self.assertIn('QFontComboBox::down-arrow', style)
        self.assertIn('chevron-down-', style)
        self.assertIn('QSpinBox::up-arrow', style)
        self.assertIn('chevron-up-', style)
        self.assertIn('QCheckBox::indicator:checked', style)
        self.assertIn('check-', style)

    def test_update_check_state_has_visible_feedback_and_cancel(self):
        self.dialog.tab_widget.setCurrentIndex(2)
        self.dialog.on_manual_check_update()
        self.app.processEvents()
        self.assertFalse(self.dialog.check_update_btn.isEnabled())
        self.assertFalse(self.dialog.cancel_check_btn.isHidden())
        self.assertFalse(self.dialog.check_progress_bar.isHidden())
        self.assertEqual(self.dialog.update_status_label.property('status'), 'working')
        self.assertEqual(self.manager.update_checks, [{'manual': True, 'source': 'settings'}])
        self.dialog.on_cancel_check_update()
        self.assertTrue(self.manager.cancelled)

    def test_dynamic_update_result_remains_reachable_at_minimum_size(self):
        self.dialog.tab_widget.setCurrentIndex(2)
        page = self.dialog.tab_widget.currentWidget()
        self.assertIsInstance(page, QScrollArea)
        self.dialog.show_inline_update_info(
            {'version': '9.9.9', 'tag': 'v9.9.9', 'body': '\n'.join(['更新说明'] * 20)},
            '1.7.7',
        )
        self.dialog.resize(self.dialog.minimumSize())
        self.app.processEvents()
        self.assertTrue(self.dialog.inline_update_group.isVisible())
        self.assertGreater(page.verticalScrollBar().maximum(), 0)
        page.verticalScrollBar().setValue(page.verticalScrollBar().maximum())
        self.app.processEvents()
        install_origin = self.dialog.install_update_btn.mapTo(page.viewport(), QPoint(0, 0))
        self.assertGreaterEqual(install_origin.y() + self.dialog.install_update_btn.height(), 0)
        self.assertLessEqual(install_origin.y(), page.viewport().height())

    def test_sync_controls_preserve_configuration_contract(self):
        self.dialog.sync_enabled_cb.setChecked(True)
        self.dialog.sync_provider_combo.setCurrentIndex(1)
        self.dialog.auto_sync_cb.setChecked(True)
        self.dialog.sync_interval_spin.setValue(1440)
        self.assertTrue(self.manager.config.get('sync.enabled'))
        self.assertEqual(self.manager.config.get('sync.provider'), 'local')
        self.assertTrue(self.manager.config.get('sync.auto_sync'))
        self.assertEqual(self.manager.config.get('sync.sync_interval_minutes'), 1440)

    def test_webdav_password_is_saved_with_dpapi_not_plaintext(self):
        from unittest.mock import patch
        self.dialog.webdav_pwd.setText('correct horse battery staple')
        with patch('core.settings.QMessageBox.information'):
            self.dialog._on_save_webdav()
        stored = self.manager.config.get('sync.webdav.password_encrypted')
        self.assertTrue(stored.startswith('dpapi:v1:'))
        self.assertNotIn('correct horse', stored)
        self.assertEqual(reveal_secret(stored), 'correct horse battery staple')
        self.assertEqual(self.manager.config.get('sync.webdav.password'), '')
        self.assertGreater(self.manager.sync_setup_count, 0)

    def test_shortcut_rows_have_separate_non_overlapping_actions(self):
        self.dialog.tab_widget.setCurrentIndex(6)
        self.app.processEvents()
        self.assertEqual(len(self.dialog._shortcut_editors), 4)
        for action_name, (badge, record_button) in self.dialog._shortcut_editors.items():
            self.assertTrue(badge.property('shortcutBadge'), action_name)
            self.assertGreaterEqual(badge.height(), 32)
            self.assertGreaterEqual(record_button.minimumWidth(), 76)
            self.assertTrue(record_button.accessibleName())
            parent_rect = badge.parentWidget().contentsRect()
            self.assertLessEqual(badge.geometry().bottom(), parent_rect.bottom())
            self.assertLessEqual(record_button.geometry().bottom(), parent_rect.bottom())

    def test_shortcut_conflict_details_scroll_instead_of_clipping_rows(self):
        self.dialog.tab_widget.setCurrentIndex(6)
        for badge, _ in self.dialog._shortcut_editors.values():
            badge.setText('Ctrl+Alt+N')
        self.assertFalse(self.dialog._save_shortcuts())
        self.app.processEvents()
        self.assertGreater(
            self.dialog.shortcuts_scroll.verticalScrollBar().maximum(), 0,
        )
        self.assertIn('与“新建便签”重复', self.dialog.shortcut_status_label.text())

    def test_shortcut_reset_waits_for_save_before_persisting(self):
        self.dialog.tab_widget.setCurrentIndex(6)
        badge, _ = self.dialog._shortcut_editors['add_note']
        badge.setText('Ctrl+Alt+N')
        self.manager.config.set('shortcuts.add_note', 'Ctrl+Alt+N')
        reset_button = next(
            button for button in self.dialog.findChildren(QPushButton)
            if button.accessibleName() == '重置新建便签快捷键'
        )
        reset_button.click()
        self.assertEqual(badge.text(), 'Ctrl+Shift+N')
        self.assertEqual(
            self.manager.config.get('shortcuts.add_note'), 'Ctrl+Alt+N',
        )
        self.assertIn('新建便签已恢复', self.dialog.shortcut_status_label.text())
        self.assertIn('保存快捷键', self.dialog.shortcut_status_label.text())

    def test_visible_page_controls_stay_inside_dialog_at_minimum_size(self):
        def is_reachable_but_clipped(widget, page):
            ancestor = widget.parentWidget()
            while ancestor is not None:
                if isinstance(ancestor, QScrollArea):
                    widget_rect = QRect(
                        widget.mapTo(ancestor.viewport(), QPoint(0, 0)),
                        widget.size(),
                    )
                    if not widget_rect.intersects(ancestor.viewport().rect()):
                        self.assertGreater(ancestor.verticalScrollBar().maximum(), 0)
                        return True
                    return False
                if ancestor is page:
                    break
                ancestor = ancestor.parentWidget()
            return False

        self.dialog.resize(self.dialog.minimumSize())
        self.app.processEvents()
        for page_index in range(self.dialog.tab_widget.count()):
            self.dialog.tab_widget.setCurrentIndex(page_index)
            self.app.processEvents()
            page = self.dialog.tab_widget.currentWidget()
            for button in page.findChildren(QPushButton):
                if not button.isVisible():
                    continue
                if is_reachable_but_clipped(button, page):
                    continue
                origin = button.mapTo(self.dialog, QPoint(0, 0))
                self.assertGreaterEqual(origin.x(), 0, button.text())
                self.assertGreaterEqual(origin.y(), 0, button.text())
                self.assertLessEqual(origin.x() + button.width(), self.dialog.width(), button.text())
                self.assertLessEqual(origin.y() + button.height(), self.dialog.height(), button.text())

            for control_type in (QComboBox, QSpinBox, QCheckBox):
                for control in page.findChildren(control_type):
                    if not control.isVisible():
                        continue
                    if is_reachable_but_clipped(control, page):
                        continue
                    origin = control.mapTo(self.dialog, QPoint(0, 0))
                    label = control.objectName() or control.__class__.__name__
                    self.assertGreaterEqual(origin.x(), 0, label)
                    self.assertGreaterEqual(origin.y(), 0, label)
                    self.assertLessEqual(
                        origin.x() + control.width(), self.dialog.width(), label
                    )
                    self.assertLessEqual(
                        origin.y() + control.height(), self.dialog.height(), label
                    )

            visible_buttons = [button for button in page.findChildren(QPushButton) if button.isVisible()]
            for index, first in enumerate(visible_buttons):
                for second in visible_buttons[index + 1:]:
                    if first.parentWidget() is not second.parentWidget():
                        continue
                    self.assertFalse(
                        first.geometry().intersects(second.geometry()),
                        f'按钮重叠: {first.text()} / {second.text()}',
                    )

    def test_reference_sizes_keep_all_pages_scrollable_and_rows_separated(self):
        """Reference Windows sizes must never compress a control into its row."""
        for width, height in ((760, 580), (820, 640)):
            with self.subTest(size=(width, height)):
                self.dialog.resize(width, height)
                self.app.processEvents()
                self.assertGreaterEqual(self.dialog.width(), width)
                self.assertGreaterEqual(self.dialog.height(), height)

                for page_index in range(self.dialog.tab_widget.count()):
                    self.dialog.tab_widget.setCurrentIndex(page_index)
                    self.app.processEvents()
                    page = self.dialog.tab_widget.currentWidget()
                    scrolls = []
                    if isinstance(page, QScrollArea):
                        scrolls.append(page)
                    scrolls.extend(page.findChildren(QScrollArea))
                    self.assertTrue(scrolls, f'第 {page_index} 页缺少滚动容器')

                    # Check controls that share a form/group parent in dialog
                    # coordinates.  Different layout rows may use different
                    # wrapper widgets, so comparing their global rectangles
                    # catches the actual visible overlap without rejecting a
                    # deliberate label/control pairing.
                    controls = page.findChildren(
                        (QLineEdit, QComboBox, QSpinBox, QCheckBox, QPushButton)
                    )
                    controls = [control for control in controls if control.isVisible()]
                    for index, first in enumerate(controls):
                        first_rect = QRect(
                            first.mapTo(self.dialog, QPoint(0, 0)), first.size()
                        )
                        for second in controls[index + 1:]:
                            if first.parentWidget() is not second.parentWidget():
                                continue
                            second_rect = QRect(
                                second.mapTo(self.dialog, QPoint(0, 0)), second.size()
                            )
                            self.assertFalse(
                                first_rect.intersects(second_rect),
                                f'控件重叠: {first.objectName()} / {second.objectName()}',
                            )

                # The two historically fragile pages get an explicit global
                # rectangle assertion for their stacked fields.
                self.dialog.tab_widget.setCurrentIndex(1)
                self.app.processEvents()
                font_fields = [
                    self.dialog.font_family_combo, self.dialog.font_size_spinbox,
                ]
                font_rects = [
                    QRect(field.mapTo(self.dialog, QPoint(0, 0)), field.size())
                    for field in font_fields
                ]
                self.assertFalse(font_rects[0].intersects(font_rects[1]))
                self.assertGreaterEqual(self.dialog.font_family_combo.height(), 34)
                self.assertGreaterEqual(self.dialog.font_size_spinbox.height(), 34)

                self.dialog.tab_widget.setCurrentIndex(4)
                self.app.processEvents()
                webdav_fields = [
                    self.dialog.webdav_url, self.dialog.webdav_user,
                    self.dialog.webdav_pwd, self.dialog.webdav_path,
                ]
                webdav_rects = [
                    QRect(field.mapTo(self.dialog, QPoint(0, 0)), field.size())
                    for field in webdav_fields
                ]
                for index, first_rect in enumerate(webdav_rects):
                    self.assertGreaterEqual(webdav_fields[index].width(), 200)
                    self.assertGreaterEqual(webdav_fields[index].height(), 34)
                    for second_rect in webdav_rects[index + 1:]:
                        self.assertFalse(first_rect.intersects(second_rect))
                save_rect = QRect(
                    self.dialog.save_webdav_btn.mapTo(self.dialog, QPoint(0, 0)),
                    self.dialog.save_webdav_btn.size(),
                )
                self.assertGreaterEqual(self.dialog.save_webdav_btn.height(), 36)
                self.assertTrue(all(not save_rect.intersects(rect) for rect in webdav_rects))


class TestSettingsThemeTokens(unittest.TestCase):
    def test_light_dark_and_high_contrast_palettes_are_distinct(self):
        light = _settings_tokens('soft_yellow.css')
        dark = _settings_tokens('dark_modern.css')
        contrast = _settings_tokens('high_contrast.css')
        self.assertFalse(light['dark'])
        self.assertTrue(dark['dark'])
        self.assertTrue(contrast['high_contrast'])
        self.assertNotEqual(light['canvas'], light['surface_alt'])
        self.assertNotEqual(dark['canvas'], dark['surface_alt'])

    def test_every_preset_theme_meets_text_contrast_floor(self):
        theme_files = sorted(
            filename for filename in os.listdir(get_styles_dir())
            if filename.endswith('.css')
        )
        self.assertGreaterEqual(len(theme_files), 3)
        for filename in theme_files:
            with self.subTest(theme=filename):
                tokens = _settings_tokens(filename)
                surface = QColor(tokens['surface'])
                self.assertGreaterEqual(
                    _contrast_ratio(QColor(tokens['text']), surface), 4.5,
                    f'{filename}: 正文文字对比度不足',
                )
                self.assertGreaterEqual(
                    _contrast_ratio(QColor(tokens['muted']), surface), 4.5,
                    f'{filename}: 辅助文字对比度不足',
                )
                self.assertGreaterEqual(
                    _contrast_ratio(QColor(tokens['accent_text']), QColor(tokens['accent'])),
                    4.5,
                    f'{filename}: 主按钮文字对比度不足',
                )


class TestSecretStorage(unittest.TestCase):
    def test_dpapi_round_trip_and_legacy_migration(self):
        protected = protect_secret('便签同步密钥')
        self.assertNotEqual(protected, '便签同步密钥')
        self.assertEqual(reveal_secret(protected), '便签同步密钥')
        self.assertEqual(reveal_secret('legacy plaintext'), 'legacy plaintext')


if __name__ == '__main__':
    unittest.main(verbosity=2)

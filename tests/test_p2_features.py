# -*- coding: utf-8 -*-
"""
P2 功能增强全面测试套件
"""

import sys
import os
import json
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
_app = QApplication.instance()
if _app is None:
    _app = QApplication(sys.argv)

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor


# ==================== 1. 富文本工具栏增强 ====================

class TestRichTextActions(unittest.TestCase):
    def setUp(self):
        from features.richtext import RichTextActions
        from core.note import PlainTextEdit
        self.editor = PlainTextEdit()
        self.editor.setPlainText("Hello World\nSecond Line")
        self.rta = RichTextActions(self.editor)

    def test_toggle_underline(self):
        cursor = self.editor.textCursor()
        cursor.select(cursor.Document)
        self.editor.setTextCursor(cursor)
        self.rta.toggle_underline()
        fmt = self.editor.textCursor().charFormat()
        self.assertTrue(fmt.fontUnderline())

    def test_toggle_strikethrough(self):
        cursor = self.editor.textCursor()
        cursor.select(cursor.Document)
        self.editor.setTextCursor(cursor)
        self.rta.toggle_strikethrough()
        fmt = self.editor.textCursor().charFormat()
        self.assertTrue(fmt.fontStrikeOut())

    def test_toggle_superscript(self):
        from PyQt5.QtGui import QTextCharFormat
        cursor = self.editor.textCursor()
        cursor.select(cursor.Document)
        self.editor.setTextCursor(cursor)
        self.rta.toggle_superscript()
        fmt = self.editor.textCursor().charFormat()
        self.assertEqual(fmt.verticalAlignment(), QTextCharFormat.AlignSuperScript)

    def test_toggle_subscript(self):
        from PyQt5.QtGui import QTextCharFormat
        cursor = self.editor.textCursor()
        cursor.select(cursor.Document)
        self.editor.setTextCursor(cursor)
        self.rta.toggle_subscript()
        fmt = self.editor.textCursor().charFormat()
        self.assertEqual(fmt.verticalAlignment(), QTextCharFormat.AlignSubScript)

    def test_set_highlight_color(self):
        cursor = self.editor.textCursor()
        cursor.select(cursor.Document)
        self.editor.setTextCursor(cursor)
        self.rta.set_highlight_color(QColor('#FFFF00'))
        fmt = self.editor.textCursor().charFormat()
        self.assertTrue(fmt.background().color().isValid())

    def test_set_alignment_center(self):
        self.rta.set_alignment(Qt.AlignCenter)
        cursor = self.editor.textCursor()
        self.assertEqual(cursor.blockFormat().alignment(), Qt.AlignCenter)

    def test_insert_unordered_list(self):
        self.rta.insert_unordered_list()
        self.assertIsNotNone(self.editor.textCursor().currentList())

    def test_insert_ordered_list(self):
        self.rta.insert_ordered_list()
        self.assertIsNotNone(self.editor.textCursor().currentList())

    def test_insert_hyperlink(self):
        self.rta.insert_hyperlink("https://example.com", "Example")
        self.assertIn("https://example.com", self.editor.toHtml())

    def test_get_current_format_state(self):
        state = self.rta.get_current_format_state()
        self.assertIsInstance(state, dict)
        for key in ('bold', 'italic', 'underline'):
            self.assertIn(key, state)


class TestImageHandler(unittest.TestCase):
    def test_init(self):
        from features.image_handler import ImageHandler
        temp_dir = tempfile.mkdtemp()
        try:
            handler = ImageHandler(temp_dir)
            self.assertIsNotNone(handler)
            self.assertEqual(handler.strategy, 'base64')
        finally:
            shutil.rmtree(temp_dir)

    def test_prepare_image_base64(self):
        from features.image_handler import ImageHandler
        temp_dir = tempfile.mkdtemp()
        try:
            handler = ImageHandler(temp_dir, strategy='base64')
            img_path = os.path.join(temp_dir, 'test.png')
            from PyQt5.QtGui import QPixmap
            pixmap = QPixmap(10, 10)
            pixmap.fill(QColor('#FF0000'))
            pixmap.save(img_path, 'PNG')
            result = handler.prepare_image(img_path, note_id=1)
            self.assertIsNotNone(result)
            self.assertTrue(len(result) > 0)
        finally:
            shutil.rmtree(temp_dir)


# ==================== 2. Markdown 渲染模式 ====================

class TestMarkdownRenderer(unittest.TestCase):
    def setUp(self):
        from features.markdown_renderer import MarkdownRenderer
        self.renderer = MarkdownRenderer()

    def test_render_heading(self):
        html = self.renderer.render("# Hello")
        self.assertIn("<h1", html)
        self.assertIn("Hello", html)

    def test_render_bold_italic(self):
        html = self.renderer.render("**bold** and *italic*")
        self.assertIn("<strong>", html)
        self.assertIn("<em>", html)

    def test_render_list(self):
        html = self.renderer.render("- item1\n- item2")
        self.assertIn("<li>", html)

    def test_render_code_block(self):
        html = self.renderer.render("```python\nprint('hello')\n```")
        self.assertIn("print", html)

    def test_render_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = self.renderer.render(md)
        self.assertIn("<table>", html)

    def test_render_body_only(self):
        html = self.renderer.render_body_only("test")
        self.assertNotIn("<html>", html)
        self.assertIn("test", html)

    def test_is_available(self):
        self.assertTrue(self.renderer.is_available())


class TestPDFExporter(unittest.TestCase):
    def test_is_available(self):
        from features.pdf_exporter import PDFExporter
        self.assertTrue(PDFExporter.is_available())

    @patch('features.pdf_exporter.QFileDialog')
    @patch('features.pdf_exporter.QMessageBox')
    def test_export_note_to_pdf(self, mock_msg, mock_dialog):
        from features.pdf_exporter import PDFExporter
        temp_dir = tempfile.mkdtemp()
        try:
            pdf_path = os.path.join(temp_dir, 'test.pdf')
            mock_dialog.getSaveFileName.return_value = (pdf_path, 'PDF (*.pdf)')
            result = PDFExporter.export_note_to_pdf("测试", "<h1>内容</h1>")
            self.assertTrue(result)
            self.assertTrue(os.path.exists(pdf_path))
        finally:
            shutil.rmtree(temp_dir)


# ==================== 3. 便签关联与链接 ====================

class TestNoteLinkManager(unittest.TestCase):
    def setUp(self):
        from features.linking import NoteLinkManager
        self.temp_dir = tempfile.mkdtemp()
        self.lm = NoteLinkManager(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_parse_links(self):
        links = self.lm.parse_links("引用 [[便签B]] 和 [[便签C]]")
        self.assertEqual(len(links), 2)
        self.assertIn("便签B", links)
        self.assertIn("便签C", links)

    def test_update_index(self):
        self.lm.update_index("1", "便签A", "引用 [[便签B]]")
        self.lm.save_index()
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, 'links_index.json')))

    def test_get_backlinks(self):
        self.lm.update_index("1", "便签A", "引用 [[便签B]]")
        self.lm.update_index("2", "便签C", "引用 [[便签B]]")
        backlinks = self.lm.get_backlinks("便签B")
        self.assertEqual(len(backlinks), 2)

    def test_remove_note(self):
        self.lm.update_index("1", "便签A", "引用 [[便签B]]")
        self.lm.remove_note("1")
        self.assertEqual(len(self.lm.get_backlinks("便签B")), 0)

    def test_no_links(self):
        self.assertEqual(len(self.lm.parse_links("普通文本")), 0)


# ==================== 4. 便签锁定/密码保护 ====================

class TestNoteEncryption(unittest.TestCase):
    def setUp(self):
        from features.encryption import NoteEncryption
        self.enc = NoteEncryption()

    def test_generate_salt(self):
        salt = self.enc.generate_salt()
        self.assertIsInstance(salt, bytes)
        self.assertEqual(len(salt), 16)

    def test_derive_key(self):
        salt = self.enc.generate_salt()
        key = self.enc.derive_key("password123", salt)
        self.assertIsInstance(key, bytes)
        self.assertEqual(len(key), 32)

    def test_encrypt_decrypt_roundtrip(self):
        """encrypt_content(plaintext, password) → dict, decrypt_content(enc, salt, pwd) → str"""
        original = "<html><body>测试内容 Test 123</body></html>"
        result = self.enc.encrypt_content(original, "test_password")
        self.assertIsInstance(result, dict)
        self.assertIn('encrypted', result)
        self.assertIn('salt', result)
        self.assertIn('key_hash', result)
        decrypted = self.enc.decrypt_content(
            result['encrypted'], result['salt'], "test_password"
        )
        self.assertEqual(decrypted, original)

    def test_wrong_password_fails(self):
        result = self.enc.encrypt_content("secret", "correct")
        with self.assertRaises(ValueError):
            self.enc.decrypt_content(result['encrypted'], result['salt'], "wrong")

    def test_hash_password(self):
        salt = self.enc.generate_salt()
        h = self.enc.hash_password("mypassword", salt)
        self.assertIsInstance(h, str)
        self.assertGreater(len(h), 0)

    def test_verify_password(self):
        salt = self.enc.generate_salt()
        h = self.enc.hash_password("mypassword", salt)
        # verify_password(password, hash_str, salt)
        self.assertTrue(self.enc.verify_password("mypassword", h, salt))
        self.assertFalse(self.enc.verify_password("wrongpassword", h, salt))

    def test_different_salts_different_keys(self):
        salt1 = self.enc.generate_salt()
        salt2 = self.enc.generate_salt()
        self.assertNotEqual(salt1, salt2)

    def test_hash_master_password(self):
        result = self.enc.hash_master_password("master123")
        self.assertIn('hash', result)
        self.assertIn('salt', result)
        self.assertIsInstance(result['hash'], str)
        self.assertIsInstance(result['salt'], str)


# ==================== 5. 云同步 ====================

class TestSyncMetadata(unittest.TestCase):
    def setUp(self):
        from features.sync.metadata import SyncMetadata
        self.temp_dir = tempfile.mkdtemp()
        self.meta_file = os.path.join(self.temp_dir, 'sync_metadata.json')
        self.meta = SyncMetadata(self.meta_file)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_update_and_get_meta(self):
        self.meta.update_file_meta("note_1.json", local_hash="abc123")
        result = self.meta.get_file_meta("note_1.json")
        self.assertEqual(result['local_hash'], "abc123")

    def test_save_and_load(self):
        self.meta.update_file_meta("note_1.json", local_hash="h1")
        self.meta.update_file_meta("note_2.json", local_hash="h2")
        self.meta.save()
        from features.sync.metadata import SyncMetadata
        meta2 = SyncMetadata(self.meta_file)
        self.assertEqual(meta2.get_file_meta("note_1.json")['local_hash'], "h1")

    def test_remove_file(self):
        self.meta.update_file_meta("note_1.json", local_hash="h1")
        self.meta.remove_file("note_1.json")
        result = self.meta.get_file_meta("note_1.json")
        self.assertEqual(result['local_hash'], '')

    def test_compute_hash(self):
        from features.sync.metadata import SyncMetadata
        temp_file = os.path.join(self.temp_dir, 'test.json')
        with open(temp_file, 'w') as f:
            f.write('{"test": true}')
        h = SyncMetadata.compute_hash(temp_file)
        self.assertIsInstance(h, str)
        self.assertGreater(len(h), 0)


class TestConflictResolver(unittest.TestCase):
    def test_resolve_newer(self):
        from features.sync.conflict import ConflictResolver
        temp_dir = tempfile.mkdtemp()
        try:
            local = os.path.join(temp_dir, 'local.json')
            remote = os.path.join(temp_dir, 'remote.json')
            with open(local, 'w') as f:
                f.write('local')
            import time; time.sleep(0.1)
            with open(remote, 'w') as f:
                f.write('remote')
            result = ConflictResolver.resolve(local, remote, 'newer')
            self.assertEqual(result, remote)
        finally:
            shutil.rmtree(temp_dir)

    def test_resolve_local(self):
        from features.sync.conflict import ConflictResolver
        result = ConflictResolver.resolve('/a', '/b', 'local')
        self.assertEqual(result, '/a')

    def test_resolve_remote(self):
        from features.sync.conflict import ConflictResolver
        result = ConflictResolver.resolve('/a', '/b', 'remote')
        self.assertEqual(result, '/b')

    def test_create_conflict_copy(self):
        from features.sync.conflict import ConflictResolver
        temp_dir = tempfile.mkdtemp()
        try:
            src = os.path.join(temp_dir, 'note.json')
            with open(src, 'w') as f:
                f.write('content')
            conflict_path = ConflictResolver.create_conflict_copy(src, 'remote')
            self.assertTrue(os.path.exists(conflict_path))
            self.assertIn('conflict', conflict_path)
        finally:
            shutil.rmtree(temp_dir)


# ==================== 6. 插件系统 ====================

class TestPluginBase(unittest.TestCase):
    def test_cannot_instantiate_abstract(self):
        from features.plugin_system.base import PluginBase
        with self.assertRaises(TypeError):
            PluginBase(MagicMock())

    def test_concrete_plugin(self):
        from features.plugin_system.base import PluginBase
        class TestPlugin(PluginBase):
            name = 'test'
            version = '1.0'
            description = 'Test'
            def on_load(self): pass
        plugin = TestPlugin(MagicMock())
        self.assertEqual(plugin.name, 'test')


class TestPluginRegistry(unittest.TestCase):
    def setUp(self):
        from features.plugin_system.registry import PluginRegistry
        self.registry = PluginRegistry()

    def test_register_context_menu(self):
        self.registry.register('p1', 'context_menu', ('Action', lambda: None))
        self.assertEqual(len(self.registry.get_context_menu_actions()), 1)

    def test_register_event_handler(self):
        cb = MagicMock()
        self.registry.register_event_handler('p1', 'on_saved', cb)
        self.registry.dispatch_event('on_saved', 1, {})
        cb.assert_called_once()

    def test_unregister_all(self):
        self.registry.register('p1', 'context_menu', ('A', lambda: None))
        self.registry.register_event_handler('p1', 'ev', lambda: None)
        self.registry.unregister_all('p1')
        self.assertEqual(len(self.registry.get_context_menu_actions()), 0)

    def test_list_plugins(self):
        mock_plugin = MagicMock()
        mock_plugin.description = "Test"
        self.registry.register_plugin_instance('test', mock_plugin)
        plugins = self.registry.list_plugins()
        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0][0], 'test')

    def test_fire_event_alias(self):
        cb = MagicMock()
        self.registry.register_event_handler('p1', 'ev', cb)
        self.registry.fire_event('ev', 'arg')
        cb.assert_called_once_with('arg')


class TestPluginLoader(unittest.TestCase):
    def test_discover_empty(self):
        from features.plugin_system.loader import PluginLoader
        temp_dir = tempfile.mkdtemp()
        try:
            loader = PluginLoader(temp_dir, MagicMock())
            self.assertEqual(len(loader.discover_plugins()), 0)
        finally:
            shutil.rmtree(temp_dir)

    def test_discover_with_plugin(self):
        from features.plugin_system.loader import PluginLoader
        temp_dir = tempfile.mkdtemp()
        try:
            pd = os.path.join(temp_dir, 'test_plugin')
            os.makedirs(pd)
            with open(os.path.join(pd, '__init__.py'), 'w') as f:
                f.write("from features.plugin_system.base import PluginBase\n"
                        "class TP(PluginBase):\n"
                        "    name='t'; version='1'; description='t'\n"
                        "    def on_load(self): pass\n")
            loader = PluginLoader(temp_dir, MagicMock())
            self.assertIn('test_plugin', loader.discover_plugins())
        finally:
            shutil.rmtree(temp_dir)

    def test_unload_all(self):
        from features.plugin_system.loader import PluginLoader
        loader = PluginLoader('/nonexistent', MagicMock())
        loader.unload_all()


class TestPluginAPI(unittest.TestCase):
    def setUp(self):
        from features.plugin_system.api import PluginAPI
        self.mock_mgr = MagicMock()
        self.mock_mgr.notes = {
            1: MagicMock(note_data={'title': 'T1', 'content': '<html>C</html>', 'plain_content': 'C'}),
        }
        self.mock_mgr.config = MagicMock()
        self.mock_mgr.config.get.return_value = {}
        self.api = PluginAPI(self.mock_mgr)

    def test_get_note_content(self):
        self.assertEqual(self.api.get_note_content(1), 'C')

    def test_get_note_title(self):
        self.assertEqual(self.api.get_note_title(1), 'T1')

    def test_get_all_note_ids(self):
        self.assertEqual(self.api.get_all_note_ids(), [1])

    def test_get_nonexistent(self):
        self.assertEqual(self.api.get_note_content(999), '')

    def test_show_notification(self):
        self.api.show_notification("T", "M")


# ==================== 7. Config P2 设置 ====================

class TestConfigP2Settings(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        from core.config import ConfigManager
        ConfigManager._instance = None
        ConfigManager._init_done = False
        with patch('core.get_user_data_dir', return_value=self.temp_dir):
            from core.config import ConfigManager as CM
            self.config = CM()

    def tearDown(self):
        from core.config import ConfigManager
        ConfigManager._instance = None
        ConfigManager._init_done = False
        shutil.rmtree(self.temp_dir)

    def test_image_defaults(self):
        self.assertEqual(self.config.get('image.strategy'), 'base64')
        self.assertEqual(self.config.get('image.max_size_kb'), 512)

    def test_security_defaults(self):
        """security 默认配置项存在于 DEFAULT_SETTINGS 中"""
        from core.config import DEFAULT_SETTINGS
        self.assertIn('security', DEFAULT_SETTINGS)
        self.assertEqual(DEFAULT_SETTINGS['security']['master_password_hash'], '')
        self.assertEqual(DEFAULT_SETTINGS['security']['master_password_salt'], '')
        self.assertFalse(DEFAULT_SETTINGS['security']['require_master_password'])

    def test_sync_defaults(self):
        self.assertFalse(self.config.get('sync.enabled'))
        self.assertEqual(self.config.get('sync.provider'), 'webdav')
        self.assertFalse(self.config.get('sync.auto_sync'))

    def test_plugins_defaults(self):
        self.assertTrue(self.config.get('plugins.enabled'))
        self.assertEqual(self.config.get('plugins.disabled'), [])

    def test_set_nested(self):
        self.config.set('security.require_master_password', True)
        self.assertTrue(self.config.get('security.require_master_password'))
        self.config.set('sync.webdav.url', 'https://dav.example.com/')
        self.assertEqual(self.config.get('sync.webdav.url'), 'https://dav.example.com/')


# ==================== 8. 集成测试 ====================

class TestNoteDefaultData(unittest.TestCase):
    def test_default_note_data_has_p2_fields(self):
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                from PyQt5.QtCore import QPoint
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(999, temp_dir, manager=None)
                data = note.note_data
                self.assertIn('locked', data)
                self.assertIn('pinned', data)
                self.assertIn('favorite', data)
                self.assertIn('always_on_top', data)
                self.assertFalse(data['locked'])
                self.assertFalse(data['pinned'])
                self.assertFalse(data['favorite'])
                self.assertTrue(data['always_on_top'])
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)


class TestEditorStackExists(unittest.TestCase):
    def test_editor_stack_created(self):
        from core.note import StickyNote
        temp_dir = tempfile.mkdtemp()
        try:
            with patch('core.note.get_position_manager') as mp:
                from PyQt5.QtCore import QPoint
                mp.return_value.get_smart_position.return_value = QPoint(100, 100)
                mp.return_value.is_position_valid.return_value = True
                note = StickyNote(998, temp_dir, manager=None)
                self.assertTrue(hasattr(note, 'editor_stack'))
                self.assertEqual(note.editor_stack.count(), 2)
                self.assertTrue(hasattr(note, 'md_preview'))
                self.assertTrue(hasattr(note, 'md_toggle_btn'))
                self.assertTrue(hasattr(note, 'backlink_btn'))
                self.assertTrue(hasattr(note, 'rich_text'))
                self.assertTrue(hasattr(note, 'md_renderer'))
                note.is_deleted = True
                note.close()
        finally:
            shutil.rmtree(temp_dir)


class TestEncryptDecryptIntegration(unittest.TestCase):
    """集成测试：完整的加密→保存→加载→解密流程"""

    def test_full_lock_unlock_cycle(self):
        from features.encryption import NoteEncryption
        enc = NoteEncryption()
        content = "<html><body>敏感内容</body></html>"
        password = "MyS3cureP@ss"

        # 加密
        result = enc.encrypt_content(content, password)
        encrypted = result['encrypted']
        salt_b64 = result['salt']
        key_hash = result['key_hash']

        # 验证密码
        self.assertTrue(enc.verify_password(password, key_hash))
        self.assertFalse(enc.verify_password("wrong", key_hash))

        # 解密
        decrypted = enc.decrypt_content(encrypted, salt_b64, password)
        self.assertEqual(decrypted, content)


if __name__ == '__main__':
    unittest.main(verbosity=2)

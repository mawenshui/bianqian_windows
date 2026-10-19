"""Exercise user-visible paste, text import and batch export paths."""

import zipfile

import pytest
from PyQt5.QtCore import QMimeData
from PyQt5.QtWidgets import QApplication

from features.formatter import ContentFormatter, SmartTextEdit
from features.import_export import ExportWorker, preview_txt_import


_app = QApplication.instance() or QApplication([])


@pytest.mark.parametrize(('content', 'kind'), [
    ('{"中文": 1}', 'json'),
    ('<div>hello</div>', 'html'),
    ('# heading', 'markdown'),
    ('a { color: red; }', 'css'),
    ('const answer = 42;', 'javascript'),
    ('def hello():\n    pass', 'python'),
    ('SELECT name FROM notes', 'sql'),
    ('just a note', 'plain'),
])
def test_content_formatter_detects_common_pasted_text(content, kind):
    formatted, actual = ContentFormatter().format_content(content)
    assert actual == kind
    assert content in formatted or kind == 'json'


def test_plain_paste_keeps_rich_clipboard_when_auto_format_disabled():
    editor = SmartTextEdit()
    mime = QMimeData()
    mime.setHtml('<b>important</b>')
    QApplication.clipboard().setMimeData(mime)
    editor.set_auto_format_enabled(False)
    editor.paste()
    assert editor.toPlainText() == 'important'
    assert editor.toHtml().find('font-weight:600') >= 0
    editor.deleteLater()


def test_plain_paste_preserves_html_only_clipboard():
    editor = SmartTextEdit()
    mime = QMimeData()
    mime.setHtml('<b>important</b>')
    QApplication.clipboard().setMimeData(mime)
    editor.paste()
    assert editor.toPlainText() == 'important'
    editor.deleteLater()


def test_txt_import_detects_repeated_file_and_continues_after_bad_encoding(tmp_path):
    first = tmp_path / 'one.txt'
    duplicate = tmp_path / 'two.txt'
    unreadable = tmp_path / 'bad.txt'
    first.write_text('Title\n=====\nBody', encoding='utf-8')
    duplicate.write_text('Title\n=====\nBody', encoding='utf-8')
    unreadable.write_bytes(b'\xff\xff')
    entries, errors = preview_txt_import([str(first), str(unreadable), str(duplicate)], [])
    assert [(entry['title'], entry['body'], entry['duplicate']) for entry in entries] == [
        ('Title', 'Body', False), ('Title', 'Body', True)]
    assert len(errors) == 1 and 'bad.txt' in errors[0]


def test_batch_markdown_export_zips_distinct_titles_and_checklists(tmp_path):
    worker = ExportWorker([
        (1, 'Same', 'First', [{'text': 'A', 'done': True}]),
        (2, 'Same', 'Second', [{'text': 'B', 'done': False}]),
    ], str(tmp_path), 'markdown')
    finished = []
    failed = []
    worker.finished.connect(finished.append)
    worker.failed.connect(failed.append)
    worker.run()
    assert not failed and len(finished) == 1
    with zipfile.ZipFile(finished[0]) as archive:
        assert set(archive.namelist()) == {'Same.md', 'Same_1.md'}
        assert '- [x] A' in archive.read('Same.md').decode('utf-8')
        assert '- [ ] B' in archive.read('Same_1.md').decode('utf-8')
    assert not list(tmp_path.glob('*.md'))

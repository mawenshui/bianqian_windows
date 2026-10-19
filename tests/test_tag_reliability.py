"""Damaged tag files and interrupted writes cannot break existing notes."""

import os
from types import SimpleNamespace

import pytest

from features.tag import TagManager


def _manager(tmp_path):
    return SimpleNamespace(settings_file=str(tmp_path / 'settings.json'), notes={})


def test_invalid_tag_json_shape_does_not_crash_tag_manager(tmp_path):
    (tmp_path / 'tags.json').write_text('[]', encoding='utf-8')
    tags = TagManager(_manager(tmp_path))
    assert tags.tags == {}
    assert tags.add_tag('工作')


def test_failed_tag_write_preserves_previous_valid_file(tmp_path, monkeypatch):
    tags = TagManager(_manager(tmp_path))
    assert tags.add_tag('原有')
    before = (tmp_path / 'tags.json').read_bytes()
    def fail_replace(*_args):
        raise OSError('injected failure')
    monkeypatch.setattr('features.tag.os.replace', fail_replace)
    assert not tags.add_tag('新建')
    assert (tmp_path / 'tags.json').read_bytes() == before
    assert '新建' not in tags.tags

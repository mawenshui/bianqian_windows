"""Custom templates must survive international names and reject unsafe keys."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from features.template import TemplateDialog, TemplateManager


def _template_manager(tmp_path):
    manager = SimpleNamespace(settings_file=str(tmp_path / 'settings.json'))
    return TemplateManager(manager)


def test_custom_template_key_cannot_escape_template_directory(tmp_path):
    templates = _template_manager(tmp_path)
    with pytest.raises(ValueError):
        templates.save_custom_template('../settings', {'name': 'unsafe', 'content': 'x'})
    assert not (tmp_path / 'settings.json').exists()
    with pytest.raises(ValueError):
        templates.delete_custom_template('../settings')


def test_distinct_chinese_template_names_do_not_overwrite_each_other(tmp_path):
    templates = _template_manager(tmp_path)
    name = SimpleNamespace(text=Mock(return_value='会议记录'))
    content = SimpleNamespace(toPlainText=Mock(return_value='第一份'))
    dialog = SimpleNamespace(name_edit=name, preview_edit=content,
                             template_manager=templates, refresh_list=Mock())
    with patch('features.template.QMessageBox.information'):
        TemplateDialog.save_custom(dialog)
        name.text.return_value = '项目计划'
        content.toPlainText.return_value = '第二份'
        TemplateDialog.save_custom(dialog)
    custom = templates.custom_templates
    assert len(custom) == 2
    assert {entry['name'] for entry in custom.values()} == {'会议记录', '项目计划'}
    assert len(_template_manager(tmp_path).custom_templates) == 2


def test_malformed_custom_template_is_ignored_without_hiding_valid_templates(tmp_path):
    templates = _template_manager(tmp_path)
    templates.save_custom_template('valid', {'name': 'Valid', 'content': 'text'})
    (tmp_path / 'templates' / 'broken.json').write_text('[]', encoding='utf-8')
    loaded = _template_manager(tmp_path).get_all_templates()
    assert 'valid' in loaded and 'broken' not in loaded

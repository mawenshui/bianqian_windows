"""Transfer packages reject malformed input before touching destination data."""

import json
import os
import zipfile
import hashlib

import pytest

from features.transfer_package import TransferPackageService


def _service(root):
    notes = root / 'notes'
    notes.mkdir(parents=True)
    styles = root / 'styles'
    styles.mkdir()
    return TransferPackageService(str(notes), str(root), str(styles))


_DEFAULT_MANIFEST = object()


def _package(path, files, manifest=_DEFAULT_MANIFEST):
    if manifest is _DEFAULT_MANIFEST:
        manifest = {'package_type': 'stickynote-transfer', 'schema_version': 1,
                    'files': {name: {'size': len(payload),
                                     'sha256': hashlib.sha256(payload).hexdigest()}
                              for name, payload in files.items()}}
    with zipfile.ZipFile(path, 'w') as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
        archive.writestr('manifest.json', json.dumps(manifest))


@pytest.mark.parametrize('manifest', [[], None, 'broken'])
def test_malformed_manifest_returns_validation_error(tmp_path, manifest):
    target = _service(tmp_path / 'target')
    package = tmp_path / 'invalid-manifest.zip'
    _package(package, {'notes/note_1.json': b'{}'}, manifest)
    preview = target.preview_package(str(package))
    assert not preview['valid'] and preview['errors']
    with pytest.raises(ValueError):
        target.import_package(str(package))
    assert os.listdir(target.notes_dir) == []


def test_windows_unsafe_attachment_name_is_rejected_before_import(tmp_path):
    target = _service(tmp_path / 'target')
    relative = 'attachments/note_1/' + 'a' * 32 + '_file:stream.txt'
    note = json.dumps({'attachments': [{'path': relative}]}).encode()
    package = tmp_path / 'unsafe.zip'
    _package(package, {'notes/note_1.json': note, 'notes/' + relative: b'payload'})
    assert not target.preview_package(str(package))['valid']
    assert os.listdir(target.notes_dir) == []


def test_export_missing_custom_theme_does_not_publish_broken_package(tmp_path):
    source = _service(tmp_path / 'source')
    (tmp_path / 'source' / 'notes' / 'note_1.json').write_text(
        json.dumps({'title': 'theme', 'theme': 'missing.css'}), encoding='utf-8')
    package = tmp_path / 'broken-export.zip'
    with pytest.raises(ValueError, match='主题'):
        source.export_package(str(package))
    assert not package.exists()


def test_only_marked_startup_placeholder_can_be_replaced(tmp_path):
    target = _service(tmp_path / 'target')
    placeholder = tmp_path / 'target' / 'notes' / 'note_1.json'
    data = {'title': '便签 1', 'plain_content': '', 'content': ''}
    placeholder.write_text(json.dumps(data), encoding='utf-8')
    assert target._placeholder() is None
    data['auto_placeholder'] = True
    placeholder.write_text(json.dumps(data), encoding='utf-8')
    assert target._placeholder() == str(placeholder)
    data['pinned'] = True
    placeholder.write_text(json.dumps(data), encoding='utf-8')
    assert target._placeholder() is None


def test_qt_empty_editor_placeholder_remains_importable(tmp_path, qapp):
    from core.note import StickyNote
    target = _service(tmp_path / 'target')
    note = StickyNote(1, target.notes_dir, manager=None)
    try:
        note.note_data['auto_placeholder'] = True
        note.save_note_sync()
        assert target._placeholder() == note.note_file
    finally:
        note.is_deleted = True
        note.close()


def test_imported_note_is_never_marked_as_disposable_placeholder(tmp_path):
    source = _service(tmp_path / 'source')
    (tmp_path / 'source' / 'notes' / 'note_1.json').write_text(
        json.dumps({'title': '便签 1', 'auto_placeholder': True}), encoding='utf-8')
    package = tmp_path / 'transfer.zip'
    source.export_package(str(package))
    target = _service(tmp_path / 'target')
    target.import_package(str(package))
    data = json.loads((tmp_path / 'target' / 'notes' / 'note_1.json').read_text(encoding='utf-8'))
    assert 'auto_placeholder' not in data
    assert target._placeholder() is None


def test_import_commit_failure_rolls_back_placeholder_and_tags(tmp_path, monkeypatch):
    source = _service(tmp_path / 'source')
    (tmp_path / 'source' / 'notes' / 'note_2.json').write_text(
        '{"title":"imported"}', encoding='utf-8')
    (tmp_path / 'source' / 'tags.json').write_text('{"colors":{"a":"#fff"}}', encoding='utf-8')
    package = tmp_path / 'transfer.zip'
    source.export_package(str(package))
    target = _service(tmp_path / 'target')
    placeholder = tmp_path / 'target' / 'notes' / 'note_1.json'
    placeholder.write_text(json.dumps({'title': '便签 1', 'auto_placeholder': True}), encoding='utf-8')
    old_tags = tmp_path / 'target' / 'tags.json'
    old_tags.write_text('{}', encoding='utf-8')
    original_replace = os.replace
    def fail_note_move(source_path, target_path):
        if str(target_path).endswith('note_2.json'):
            raise OSError('injected disk failure')
        return original_replace(source_path, target_path)
    monkeypatch.setattr('features.transfer_package.os.replace', fail_note_move)
    with pytest.raises(OSError, match='injected disk failure'):
        target.import_package(str(package), safety_backup=lambda: True)
    assert placeholder.exists() and not (tmp_path / 'target' / 'notes' / 'note_2.json').exists()
    assert old_tags.read_text(encoding='utf-8') == '{}'


def test_round_trip_with_attachment_and_archived_note(tmp_path):
    source = _service(tmp_path / 'source')
    (tmp_path / 'source' / 'tags.json').write_text('{"colors":{"work":"#ffffff"}}', encoding='utf-8')
    asset = tmp_path / 'source' / 'notes' / 'attachments' / 'note_1' / ('a' * 32 + '_file.txt')
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b'attachment')
    data = {'title': '完整迁移', 'plain_content': '正文', 'archived': True,
            'checklist': [{'text': 'item', 'done': False}],
            'attachments': [{'path': 'attachments/note_1/' + asset.name}]}
    (tmp_path / 'source' / 'notes' / 'note_1.json').write_text(json.dumps(data), encoding='utf-8')
    package = tmp_path / 'transfer.zip'
    assert source.export_package(str(package))['valid']
    target = _service(tmp_path / 'target')
    assert target.import_package(str(package))['note_count'] == 1
    assert json.loads((tmp_path / 'target' / 'notes' / 'note_1.json').read_text(encoding='utf-8')) == data
    assert (tmp_path / 'target' / 'notes' / 'attachments' / 'note_1' / asset.name).read_bytes() == b'attachment'
    assert (tmp_path / 'target' / 'tags.json').exists()
    with pytest.raises(ValueError, match='非空'):
        target.import_package(str(package))


def test_corrupt_and_traversal_packages_are_rejected(tmp_path):
    target = _service(tmp_path / 'target')
    package = tmp_path / 'bad.zip'
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr('../escape.txt', 'bad')
        archive.writestr('manifest.json', '{}')
    assert not target.preview_package(str(package))['valid']
    with pytest.raises(ValueError):
        target.import_package(str(package))
    assert not (tmp_path / 'escape.txt').exists()
    assert not os.listdir(target.notes_dir)


def test_blank_placeholder_is_replaced_only_after_safety_backup(tmp_path):
    source = _service(tmp_path / 'source')
    (tmp_path / 'source' / 'notes' / 'note_2.json').write_text('{"title":"imported"}', encoding='utf-8')
    package = tmp_path / 'transfer.zip'
    source.export_package(str(package))
    target = _service(tmp_path / 'target')
    placeholder = tmp_path / 'target' / 'notes' / 'note_1.json'
    placeholder.write_text('{"title":"便签 1","plain_content":"","content":"","auto_placeholder":true}', encoding='utf-8')
    assert target.preview_package(str(package))['destination_empty']
    with pytest.raises(RuntimeError):
        target.import_package(str(package), safety_backup=lambda: False)
    assert placeholder.exists()
    target.import_package(str(package), safety_backup=lambda: True)
    assert not placeholder.exists()
    assert (tmp_path / 'target' / 'notes' / 'note_2.json').exists()


def test_duplicate_member_and_missing_resource_fail_preview(tmp_path):
    target = _service(tmp_path / 'target')
    duplicate = tmp_path / 'duplicate.zip'
    with zipfile.ZipFile(duplicate, 'w') as archive:
        archive.writestr('notes/note_1.json', '{}')
        archive.writestr('notes/note_1.json', '{}')
        archive.writestr('manifest.json', '{}')
    assert '重复' in target.preview_package(str(duplicate))['errors'][0]
    source = _service(tmp_path / 'source')
    asset = tmp_path / 'source' / 'notes' / 'attachments' / 'note_1' / ('b' * 32 + '_missing.txt')
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b'present at export')
    (tmp_path / 'source' / 'notes' / 'note_1.json').write_text(json.dumps({
        'attachments': [{'path': 'attachments/note_1/' + asset.name}]}), encoding='utf-8')
    package = tmp_path / 'valid.zip'
    source.export_package(str(package))
    tampered = tmp_path / 'tampered.zip'
    with zipfile.ZipFile(package) as old, zipfile.ZipFile(tampered, 'w') as new:
        for name in old.namelist():
            if name != 'notes/attachments/note_1/' + asset.name:
                new.writestr(name, old.read(name))
    assert not target.preview_package(str(tampered))['valid']
    assert not os.listdir(target.notes_dir)


def test_import_clamps_offscreen_geometry(tmp_path, qapp):
    source = _service(tmp_path / 'source')
    (tmp_path / 'source' / 'notes' / 'note_1.json').write_text(json.dumps({
        'title': 'portable',
        'geometry': {'x': 99999, 'y': 99999, 'width': 400, 'height': 300},
    }), encoding='utf-8')
    package = tmp_path / 'transfer.zip'
    source.export_package(str(package))
    target = _service(tmp_path / 'target')
    target.import_package(str(package))
    data = json.loads((tmp_path / 'target' / 'notes' / 'note_1.json').read_text(encoding='utf-8'))
    area = qapp.primaryScreen().availableGeometry()
    assert area.left() <= data['geometry']['x'] <= area.right()
    assert area.top() <= data['geometry']['y'] <= area.bottom()

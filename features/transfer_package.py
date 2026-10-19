# -*- coding: utf-8 -*-
"""Offline, lossless note transfer package for an empty destination library."""

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone

from core import __version__, get_styles_dir, get_user_data_dir
from features.attachments import attachment_path


_NOTE = re.compile(r'notes/note_[1-9]\d*\.json$')
_ASSET = re.compile(r'notes/(?:attachments/note_[1-9]\d*/[0-9a-f]{32}_[^/\\]+|images/background_[1-9]\d*_[^/\\]+)$')
_STYLE = re.compile(r'styles/[A-Za-z0-9_.-]+\.css$')
_LIMIT = 512 * 1024 * 1024


def _safe_asset_name(name):
    """Reject names Windows cannot store as ordinary files (including ADS)."""
    basename = name.rsplit('/', 1)[-1]
    return (bool(basename) and not basename.endswith((' ', '.'))
            and not any(ord(char) < 32 or char in '<>:"|?*' for char in basename))


class TransferPackageService:
    def __init__(self, notes_dir, data_dir=None, styles_dir=None):
        self.notes_dir = os.path.realpath(notes_dir)
        self.data_dir = os.path.realpath(data_dir or get_user_data_dir())
        self.styles_dir = os.path.realpath(styles_dir or get_styles_dir())

    @staticmethod
    def _note_files(notes_dir):
        if not os.path.isdir(notes_dir):
            return []
        return sorted(name for name in os.listdir(notes_dir)
                      if re.fullmatch(r'note_[1-9]\d*\.json', name))

    def _placeholder(self):
        names = self._note_files(self.notes_dir)
        if len(names) != 1:
            return None
        path = os.path.join(self.notes_dir, names[0])
        try:
            with open(path, encoding='utf-8') as stream:
                data = json.load(stream)
            note_id = int(names[0][5:-5])
            content = data.get('content') or ''
            if not isinstance(content, str):
                return None
            # Qt serializes an empty rich-text editor as nonempty HTML.
            from PyQt5.QtGui import QTextDocument
            document = QTextDocument()
            document.setHtml(content)
            blank_html = (not document.toPlainText().strip()
                          and not re.search(r'<(?:img|object|iframe|svg|video|audio|table)\b',
                                            content, re.IGNORECASE))
            defaults = {'pinned': False, 'favorite': False, 'locked': False,
                        'archived': False, 'edge_collapsed': False,
                        'theme': 'soft_yellow.css',
                        'always_on_top': True, 'background_text_color': '',
                        'background_control_color': '', 'font_color': '#000000',
                        'font_color_mode': 'theme', 'markdown_content': ''}
            if (data.get('auto_placeholder') is True
                    and data.get('title') == f'便签 {note_id}'
                    and not data.get('plain_content') and blank_html
                    and not data.get('attachments') and not data.get('checklist')
                    and not data.get('background_image') and not data.get('reminder')
                    and not data.get('tags')
                    and all(data.get(key, expected) == expected
                            for key, expected in defaults.items())
                    and abs(float(data.get('opacity', 0.9)) - 0.9) < 0.01):
                return path
        except (OSError, ValueError, TypeError):
            pass
        return None

    def export_package(self, output_path):
        """Caller flushes open notes first. ZIP is atomically published."""
        files = {}
        for name in self._note_files(self.notes_dir):
            source = os.path.join(self.notes_dir, name)
            if os.path.islink(source):
                raise ValueError('不能导出链接便签')
            with open(source, encoding='utf-8') as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                raise ValueError(f'便签数据无效: {name}')
            files['notes/' + name] = source
            for entry in data.get('attachments', []):
                relative = entry.get('path', '') if isinstance(entry, dict) else ''
                if not _ASSET.fullmatch('notes/' + relative) or not _safe_asset_name(relative):
                    raise ValueError(f'附件路径无效: {relative}')
                path = attachment_path(self.notes_dir, relative)
                if not os.path.isfile(path) or os.path.islink(path):
                    raise ValueError(f'附件缺失或无效: {relative}')
                files['notes/' + relative] = path
            background = data.get('background_image', '')
            if background:
                if (not re.fullmatch(r'images/background_[1-9]\d*_[^/\\]+', background)
                        or not _safe_asset_name(background)):
                    raise ValueError('背景路径无效')
                path = os.path.join(self.notes_dir, *background.split('/'))
                if not os.path.isfile(path) or os.path.islink(path):
                    raise ValueError(f'背景图片缺失: {background}')
                files['notes/' + background] = path
            theme = data.get('theme', '')
            if theme:
                if not isinstance(theme, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.css', theme):
                    raise ValueError(f'主题路径无效: {theme}')
                path = os.path.join(self.styles_dir, theme)
                if not os.path.isfile(path) or os.path.islink(path):
                    raise ValueError(f'主题资源缺失: {theme}')
                files['styles/' + theme] = path
        tags = os.path.join(self.data_dir, 'tags.json')
        if os.path.isfile(tags) and not os.path.islink(tags):
            files['tags.json'] = tags
        if not any(_NOTE.fullmatch(name) for name in files):
            raise ValueError('没有可导出的便签')
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        temporary = output_path + '.' + uuid.uuid4().hex + '.tmp'
        manifest = {'package_type': 'stickynote-transfer', 'schema_version': 1,
                    'app_version': __version__,
                    'created_at': datetime.now(timezone.utc).isoformat(), 'files': {}}
        try:
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, path in sorted(files.items()):
                    with open(path, 'rb') as stream:
                        payload = stream.read()
                    manifest['files'][name] = {'size': len(payload),
                                               'sha256': hashlib.sha256(payload).hexdigest()}
                    archive.writestr(name, payload)
                archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False).encode('utf-8'))
            os.replace(temporary, output_path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        return self.preview_package(output_path)

    def preview_package(self, path):
        result = {'valid': False, 'errors': [], 'note_count': 0,
                  'attachment_count': 0, 'style_count': 0, 'size': 0,
                  'destination_empty': (not bool(self._note_files(self.notes_dir))
                                        or self._placeholder() is not None)}
        try:
            with zipfile.ZipFile(path) as archive:
                entries = [i for i in archive.infolist() if not i.is_dir()]
                names = [i.filename for i in entries]
                if len(names) != len(set(names)) or len(entries) > 10000:
                    raise ValueError('包包含重复或过多文件')
                if not names or 'manifest.json' not in names:
                    raise ValueError('缺少迁移清单')
                result['size'] = sum(i.file_size for i in entries)
                if result['size'] > _LIMIT:
                    raise ValueError('解压数据超过 512 MB')
                for info in entries:
                    name = info.filename
                    if not (name in ('manifest.json', 'tags.json') or _NOTE.fullmatch(name)
                            or (_ASSET.fullmatch(name) and _safe_asset_name(name))
                            or _STYLE.fullmatch(name)):
                        raise ValueError(f'不安全或未知路径: {name}')
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError(f'不允许符号链接: {name}')
                if archive.testzip() is not None:
                    raise ValueError('ZIP CRC 校验失败')
                manifest = json.loads(archive.read('manifest.json'))
                if not isinstance(manifest, dict) or manifest.get('package_type') != 'stickynote-transfer' or manifest.get('schema_version') != 1:
                    raise ValueError('未知迁移包版本')
                expected = manifest.get('files')
                if not isinstance(expected, dict) or set(expected) != set(names) - {'manifest.json'}:
                    raise ValueError('文件清单不匹配')
                for name, meta in expected.items():
                    payload = archive.read(name)
                    if not isinstance(meta, dict) or meta.get('size') != len(payload) or meta.get('sha256') != hashlib.sha256(payload).hexdigest():
                        raise ValueError(f'文件校验失败: {name}')
                note_names = [name for name in names if _NOTE.fullmatch(name)]
                if not note_names:
                    raise ValueError('迁移包没有便签')
                referenced = set()
                for name in note_names:
                    data = json.loads(archive.read(name))
                    if not isinstance(data, dict):
                        raise ValueError(f'便签格式无效: {name}')
                    note_id = int(name[11:-5])
                    for entry in data.get('attachments', []):
                        relative = entry.get('path', '') if isinstance(entry, dict) else ''
                        asset = 'notes/' + relative
                        if (not _ASSET.fullmatch(asset) or not _safe_asset_name(asset)
                                or not asset.startswith(f'notes/attachments/note_{note_id}/')):
                            raise ValueError(f'附件路径无效: {name}')
                        referenced.add(asset)
                    background = data.get('background_image', '')
                    if background:
                        asset = 'notes/' + background
                        if (not _ASSET.fullmatch(asset) or not _safe_asset_name(asset)
                                or not asset.startswith(f'notes/images/background_{note_id}_')):
                            raise ValueError(f'背景路径无效: {name}')
                        referenced.add(asset)
                    theme = data.get('theme', '')
                    if theme and not re.fullmatch(r'[A-Za-z0-9_.-]+\.css', theme):
                        raise ValueError(f'主题路径无效: {name}')
                    if theme and 'styles/' + theme not in names and not os.path.isfile(os.path.join(self.styles_dir, theme)):
                        raise ValueError(f'主题资源缺失: {theme}')
                missing = referenced - set(names)
                if missing:
                    raise ValueError('引用资源缺失: ' + sorted(missing)[0])
                if 'tags.json' in names and not isinstance(json.loads(archive.read('tags.json')), dict):
                    raise ValueError('标签格式无效')
                result['note_count'] = len(note_names)
                result['attachment_count'] = sum('/attachments/' in n for n in names)
                result['style_count'] = sum(n.startswith('styles/') for n in names)
                result['valid'] = True
        except (OSError, ValueError, TypeError, KeyError, RuntimeError,
                zipfile.BadZipFile, json.JSONDecodeError) as exc:
            result['errors'].append(str(exc))
        return result

    def import_package(self, path, safety_backup=None):
        """Import only into an empty library; preserve files on every failure."""
        preview = self.preview_package(path)
        if not preview['valid']:
            raise ValueError('; '.join(preview['errors']))
        if not preview['destination_empty']:
            raise ValueError('目标便签库非空，请先使用独立合并流程')
        if safety_backup is not None and not safety_backup():
            raise RuntimeError('导入前安全备份失败')
        placeholder = self._placeholder()
        with tempfile.TemporaryDirectory(prefix='transfer_', dir=self.data_dir) as temporary:
            stable_package = os.path.join(temporary, 'validated-package.zip')
            shutil.copy2(path, stable_package)
            verified = self.preview_package(stable_package)
            if not verified['valid']:
                raise ValueError('迁移包在导入前已变化: ' + '; '.join(verified['errors']))
            stage = os.path.join(temporary, 'stage')
            os.makedirs(stage)
            with zipfile.ZipFile(stable_package) as archive:
                for name in archive.namelist():
                    if name == 'manifest.json' or name.endswith('/'):
                        continue
                    target = os.path.join(stage, *name.split('/'))
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, 'wb') as stream:
                        stream.write(archive.read(name))
            self._adapt_window_geometry(stage)
            moved = []
            parked = None
            parked_tags = None
            try:
                if placeholder:
                    parked = os.path.join(temporary, 'placeholder.json')
                    os.replace(placeholder, parked)
                tags_target = os.path.join(self.data_dir, 'tags.json')
                if os.path.isfile(tags_target) and os.path.isfile(os.path.join(stage, 'tags.json')):
                    with open(tags_target, encoding='utf-8') as stream:
                        existing_tags = json.load(stream)
                    if existing_tags != {}:
                        raise FileExistsError('目标标签库非空')
                    parked_tags = os.path.join(temporary, 'prior_tags.json')
                    os.replace(tags_target, parked_tags)
                for root, _, files in os.walk(stage):
                    for name in files:
                        source = os.path.join(root, name)
                        relative = os.path.relpath(source, stage).replace('\\', '/')
                        if relative.startswith('notes/'):
                            target = os.path.join(self.notes_dir, *relative.split('/')[1:])
                        elif relative.startswith('styles/'):
                            target = os.path.join(self.styles_dir, name)
                        else:
                            target = os.path.join(self.data_dir, 'tags.json')
                        if os.path.exists(target):
                            if relative.startswith('styles/'):
                                if open(source, 'rb').read() == open(target, 'rb').read():
                                    continue
                            raise FileExistsError(f'目标文件已存在: {relative}')
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        os.replace(source, target)
                        moved.append(target)
            except Exception:
                for target in reversed(moved):
                    os.remove(target)
                if parked and os.path.isfile(parked):
                    os.replace(parked, placeholder)
                if parked_tags and os.path.isfile(parked_tags):
                    os.replace(parked_tags, tags_target)
                raise
        return preview

    @staticmethod
    def _adapt_window_geometry(stage):
        """Keep imported windows on a currently available screen."""
        from PyQt5.QtCore import QPoint
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        notes = os.path.join(stage, 'notes')
        for name in os.listdir(notes):
            if not _NOTE.fullmatch('notes/' + name):
                continue
            path = os.path.join(notes, name)
            with open(path, encoding='utf-8') as stream:
                data = json.load(stream)
            changed = bool(data.pop('auto_placeholder', False))
            for key in ('geometry', 'pre_hide_geometry'):
                if app is None or app.primaryScreen() is None:
                    break
                geo = data.get(key)
                if not isinstance(geo, dict):
                    continue
                try:
                    x, y = int(geo['x']), int(geo['y'])
                    width, height = max(240, int(geo['width'])), max(240, int(geo['height']))
                except (KeyError, TypeError, ValueError):
                    continue
                screen = app.screenAt(QPoint(x + width // 2, y + height // 2)) or app.primaryScreen()
                area = screen.availableGeometry()
                clamped = {
                    'x': max(area.left(), min(x, area.right() - min(width, area.width()) + 1)),
                    'y': max(area.top(), min(y, area.bottom() - min(height, area.height()) + 1)),
                    'width': min(width, area.width()), 'height': min(height, area.height()),
                }
                if clamped != geo:
                    data[key] = clamped
                    changed = True
            if changed:
                with open(path, 'w', encoding='utf-8') as stream:
                    json.dump(data, stream, ensure_ascii=False, indent=4)

# -*- coding: utf-8 -*-
"""Bounded, local revisions for an individual note.

The current note file remains authoritative.  Each revision is a self-contained
snapshot, including referenced resources, so deleting an attachment cannot make
an older revision impossible to restore.  No note data is sent over the network.
"""

import base64
import copy
import hashlib
import io
import json
import logging
import os
import re
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidTag

from features.attachments import attachment_path


logger = logging.getLogger(__name__)
_UUID = re.compile(r'^[0-9a-f]{32}$')
_SNAP = re.compile(r'^\d{8}T\d{6}_\d{6}_[0-9a-f]{12}\.snap$')
_SEMANTIC = ('title', 'content', 'plain_content', 'edit_mode',
             'markdown_content', 'checklist', 'tags', 'reminder',
             'attachments', 'background_image')
_MAX_PER_NOTE = 20
_MAX_BYTES = 200 * 1024 * 1024
_MAX_AGE = timedelta(days=30)


class HistoryLockedError(RuntimeError):
    """History has a password wrapper but has not been unlocked this run."""


def _atomic_bytes(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.history_', suffix='.tmp',
                                              dir=os.path.dirname(path))
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def _derive(password, salt):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                     salt=salt, iterations=480000)
    return kdf.derive(password.encode('utf-8'))


class NoteHistoryStore:
    """Thread-safe revision store rooted beside ``notes/``."""

    def __init__(self, notes_dir):
        self.notes_dir = os.path.realpath(notes_dir)
        self.root = os.path.join(os.path.dirname(self.notes_dir), 'history')
        self._key_file = os.path.join(self.root, 'key.json')
        self._key = None
        self._lock = threading.RLock()
        self.last_warning = ''

    def _note_dir(self, note_uuid):
        if not isinstance(note_uuid, str) or not _UUID.fullmatch(note_uuid):
            raise ValueError('无效的便签历史标识')
        return os.path.join(self.root, note_uuid)

    def _paths(self, note_uuid):
        folder = self._note_dir(note_uuid)
        if not os.path.isdir(folder):
            return []
        return [os.path.join(folder, name) for name in sorted(os.listdir(folder))
                if _SNAP.fullmatch(name)]

    def _require_unlocked(self):
        if os.path.isfile(self._key_file) and self._key is None:
            raise HistoryLockedError('历史记录尚未解锁')

    def _seal(self, payload):
        if self._key is None:
            return b'P' + payload
        nonce = os.urandom(12)
        return b'E' + nonce + AESGCM(self._key).encrypt(nonce, payload, b'StickyNote history v1')

    def _open(self, envelope):
        if not envelope:
            raise ValueError('空历史记录')
        if envelope[:1] == b'P':
            return envelope[1:]
        if envelope[:1] == b'E':
            self._require_unlocked()
            if self._key is None or len(envelope) < 29:
                raise HistoryLockedError('历史记录需要主密码')
            return AESGCM(self._key).decrypt(
                envelope[1:13], envelope[13:], b'StickyNote history v1')
        raise ValueError('未知历史记录格式')

    def _wrap_key(self, password, key, previous=None):
        salt, nonce = os.urandom(16), os.urandom(12)
        wrapped = AESGCM(_derive(password, salt)).encrypt(
            nonce, key, b'StickyNote history key v1')
        entry = {'salt': base64.b64encode(salt).decode('ascii'),
                 'nonce': base64.b64encode(nonce).decode('ascii'),
                 'wrapped': base64.b64encode(wrapped).decode('ascii')}
        wraps = [entry] + (previous or [])
        _atomic_bytes(self._key_file, json.dumps(
            {'format': 1, 'wraps': wraps}, ensure_ascii=False).encode('utf-8'))

    def unlock(self, password):
        """Unlock after the startup password check; retain only the data key."""
        if not password:
            raise ValueError('主密码不能为空')
        with self._lock:
            if os.path.isfile(self._key_file):
                with open(self._key_file, 'r', encoding='utf-8') as stream:
                    wraps = json.load(stream).get('wraps', [])
                for entry in wraps:
                    try:
                        key = AESGCM(_derive(password, base64.b64decode(entry['salt']))).decrypt(
                            base64.b64decode(entry['nonce']),
                            base64.b64decode(entry['wrapped']),
                            b'StickyNote history key v1')
                        self._key = key
                        break
                    except (KeyError, ValueError, TypeError, InvalidTag):
                        continue
                if self._key is None:
                    raise HistoryLockedError('主密码无法解锁历史记录')
            else:
                self._key = os.urandom(32)
                self._wrap_key(password, self._key)
            # A crash during initial protection can leave plaintext revisions.
            # Converting each file atomically makes the next unlock resumable.
            self._protect_existing()

    def _protect_existing(self):
        for note_uuid in os.listdir(self.root):
            if not _UUID.fullmatch(note_uuid):
                continue
            for path in self._paths(note_uuid):
                with open(path, 'rb') as stream:
                    raw = stream.read()
                if raw[:1] == b'P':
                    _atomic_bytes(path, self._seal(raw[1:]))

    def change_password(self, password):
        """Add a new wrapping key before the caller updates password config."""
        with self._lock:
            self._require_unlocked()
            if self._key is None:
                self._key = os.urandom(32)
            previous = []
            if os.path.isfile(self._key_file):
                with open(self._key_file, 'r', encoding='utf-8') as stream:
                    previous = json.load(stream).get('wraps', [])[:1]
            self._wrap_key(password, self._key, previous)
            self._protect_existing()

    def finalize_password_change(self):
        """Drop the former password wrapper after config accepts the new hash."""
        with self._lock:
            self._require_unlocked()
            if not os.path.isfile(self._key_file):
                return
            with open(self._key_file, 'r', encoding='utf-8') as stream:
                wraps = json.load(stream).get('wraps', [])
            if len(wraps) > 1:
                _atomic_bytes(self._key_file, json.dumps(
                    {'format': 1, 'wraps': wraps[:1]}, ensure_ascii=False).encode('utf-8'))

    def disable_password(self):
        """Decrypt revisions before the caller disables startup password."""
        with self._lock:
            self._require_unlocked()
            if not os.path.isfile(self._key_file):
                return
            for note_uuid in os.listdir(self.root):
                if not _UUID.fullmatch(note_uuid):
                    continue
                for path in self._paths(note_uuid):
                    with open(path, 'rb') as stream:
                        raw = stream.read()
                    if raw[:1] == b'E':
                        _atomic_bytes(path, b'P' + self._open(raw))
            os.remove(self._key_file)
            self._key = None

    @staticmethod
    def _semantic_hash(data):
        payload = {key: data.get(key) for key in _SEMANTIC}
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False,
            sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')).hexdigest()

    def _resources(self, data):
        result = {}
        for entry in data.get('attachments', []):
            relative = entry.get('path', '') if isinstance(entry, dict) else ''
            path = attachment_path(self.notes_dir, relative)
            with open(path, 'rb') as stream:
                result[relative] = stream.read()
        background = data.get('background_image', '')
        if background:
            if not re.fullmatch(r'images/background_\d+_[^/\\]+', background):
                raise ValueError('历史背景图片路径无效')
            path = os.path.realpath(os.path.join(self.notes_dir, *background.split('/')))
            if os.path.commonpath([path, self.notes_dir]) != self.notes_dir:
                raise ValueError('历史背景图片超出数据目录')
            with open(path, 'rb') as stream:
                result[background] = stream.read()
        return result

    def capture(self, note_id, data, force=False):
        """Record a successfully saved state; return True when a revision was added."""
        note_uuid = data.get('note_uuid')
        with self._lock:
            self._require_unlocked()
            paths = self._paths(note_uuid)
            fingerprint = self._semantic_hash(data)
            last = None
            damaged = False
            for path in reversed(paths):
                try:
                    last = self._read_payload(path)
                    break
                except (OSError, ValueError, TypeError, KeyError,
                        zipfile.BadZipFile, InvalidTag) as exc:
                    damaged = True
                    logger.warning('跳过损坏的便签历史 %s: %s', path, exc)
            if last is not None and not damaged:
                if last['fingerprint'] == fingerprint:
                    return False
                age = datetime.now(timezone.utc) - datetime.fromisoformat(last['created_at'])
                resources_changed = (last['data'].get('attachments') != data.get('attachments')
                                     or last['data'].get('background_image') != data.get('background_image'))
                if not force and age < timedelta(minutes=5) and not resources_changed:
                    return False
            resources = self._resources(data)
            copy_data = copy.deepcopy(data)
            stamp = datetime.now(timezone.utc)
            payload = {'format': 1, 'note_id': int(note_id),
                       'note_uuid': note_uuid, 'created_at': stamp.isoformat(),
                       'fingerprint': fingerprint, 'data': copy_data}
            memory = io.BytesIO()
            with zipfile.ZipFile(memory, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('note.json', json.dumps(payload, ensure_ascii=False))
                for relative, content in sorted(resources.items()):
                    archive.writestr('resources/' + relative, content)
            if memory.tell() > _MAX_BYTES:
                self.last_warning = '单个历史版本超过 200 MB，记录已暂停；便签仍正常保存。'
                logger.warning(self.last_warning)
                return False
            path = os.path.join(self._note_dir(note_uuid),
                stamp.strftime('%Y%m%dT%H%M%S_%f') + '_' + uuid.uuid4().hex[:12] + '.snap')
            _atomic_bytes(path, self._seal(memory.getvalue()))
            self.last_warning = ''
            self._prune(note_uuid)
            return True

    def _read_payload(self, path):
        with open(path, 'rb') as stream:
            raw = self._open(stream.read())
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            if 'note.json' not in names or len(names) != len(set(names)):
                raise ValueError('历史记录文件清单无效')
            payload = json.loads(archive.read('note.json'))
            if (not isinstance(payload, dict) or payload.get('format') != 1
                    or not isinstance(payload.get('data'), dict)
                    or not isinstance(payload.get('fingerprint'), str)
                    or not isinstance(payload.get('created_at'), str)):
                raise ValueError('历史记录版本或数据无效')
            created_at = datetime.fromisoformat(payload['created_at'])
            if created_at.tzinfo is None:
                raise ValueError('历史记录时间缺少时区')
            return payload

    def list_versions(self, note_uuid):
        with self._lock:
            self._require_unlocked()
            versions = []
            for path in reversed(self._paths(note_uuid)):
                try:
                    versions.append(self._read_payload(path) | {
                        'snapshot': os.path.basename(path)})
                except (OSError, ValueError, TypeError, KeyError,
                        zipfile.BadZipFile, InvalidTag) as exc:
                    self.last_warning = '部分历史版本损坏，已跳过；当前便签未受影响。'
                    logger.warning('跳过损坏的便签历史 %s: %s', path, exc)
            return versions

    def restore_data(self, note_uuid, snapshot):
        """Return a verified prior note and resources without changing the live note."""
        if not isinstance(snapshot, str) or not _SNAP.fullmatch(snapshot):
            raise ValueError('历史版本名无效')
        path = os.path.join(self._note_dir(note_uuid), snapshot)
        with self._lock:
            with open(path, 'rb') as stream:
                raw = self._open(stream.read())
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                payload = json.loads(archive.read('note.json'))
                if (not isinstance(payload, dict) or payload.get('format') != 1
                        or not isinstance(payload.get('data'), dict)):
                    raise ValueError('历史记录版本或数据无效')
                if payload.get('note_uuid') != note_uuid:
                    raise ValueError('历史记录归属不符')
                data = payload['data']
                expected = set(self._resources_paths(data))
                actual = {name[10:] for name in archive.namelist()
                          if name.startswith('resources/')}
                if expected != actual or archive.testzip() is not None:
                    raise ValueError('历史资源缺失或损坏')
                resources = {relative: archive.read('resources/' + relative)
                             for relative in expected}
                return copy.deepcopy(data), resources

    @staticmethod
    def _resources_paths(data):
        for entry in data.get('attachments', []):
            if isinstance(entry, dict):
                yield entry.get('path', '')
        background = data.get('background_image')
        if background:
            yield background

    def _prune(self, note_uuid):
        paths = self._paths(note_uuid)
        cutoff = datetime.now(timezone.utc) - _MAX_AGE
        for path in paths[:-1]:
            try:
                stamp = datetime.strptime(os.path.basename(path)[:22], '%Y%m%dT%H%M%S_%f')
                if stamp.replace(tzinfo=timezone.utc) < cutoff:
                    os.remove(path)
            except (ValueError, OSError):
                logger.warning('历史清理跳过 %s', path)
        paths = self._paths(note_uuid)
        for path in paths[:-_MAX_PER_NOTE]:
            os.remove(path)
        total = 0
        all_paths = []
        if os.path.isdir(self.root):
            for name in os.listdir(self.root):
                if _UUID.fullmatch(name):
                    all_paths.extend(self._paths(name))
        for path in all_paths:
            total += os.path.getsize(path)
        for path in sorted(all_paths)[:-1]:
            if total <= _MAX_BYTES:
                break
            size = os.path.getsize(path)
            os.remove(path)
            total -= size

    def remove_note(self, note_uuid):
        if not note_uuid or not _UUID.fullmatch(str(note_uuid)):
            return
        with self._lock:
            for path in self._paths(note_uuid):
                os.remove(path)
            folder = self._note_dir(note_uuid)
            if os.path.isdir(folder):
                os.rmdir(folder)

    def usage_bytes(self):
        total = 0
        if os.path.isdir(self.root):
            for name in os.listdir(self.root):
                if _UUID.fullmatch(name):
                    total += sum(os.path.getsize(path) for path in self._paths(name))
        return total


_stores = {}
_stores_lock = threading.Lock()


def get_history_store(notes_dir):
    """Share the session key between startup verification and note workers."""
    root = os.path.realpath(notes_dir)
    with _stores_lock:
        if root not in _stores:
            _stores[root] = NoteHistoryStore(root)
        return _stores[root]


def forget_history_store(notes_dir):
    """Discard a cached in-memory key after a full data/password reset."""
    root = os.path.realpath(notes_dir)
    with _stores_lock:
        store = _stores.pop(root, None)
        if store is not None:
            with store._lock:
                store._key = None


class NoteHistoryDialog:
    """Small revision browser; kept separate from the note's editing widget."""

    def __init__(self, manager, note_id):
        import difflib
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                     QListWidget, QListWidgetItem, QTextEdit,
                                     QPushButton, QMessageBox)

        self.manager = manager
        self.note_id = note_id
        self.dialog = QDialog()
        self.dialog.setWindowTitle('便签版本历史')
        self.dialog.resize(720, 500)
        layout = QVBoxLayout(self.dialog)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.list_widget = QListWidget()
        self.list_widget.setAccessibleName('历史版本列表')
        layout.addWidget(self.list_widget)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName('历史版本与当前内容差异')
        layout.addWidget(self.preview)
        row = QHBoxLayout()
        self.restore_button = QPushButton('恢复此版本')
        self.restore_button.setEnabled(False)
        row.addWidget(self.restore_button)
        clear_button = QPushButton('清理此便签历史')
        clear_button.clicked.connect(self._clear)
        row.addWidget(clear_button)
        close = QPushButton('关闭')
        close.clicked.connect(self.dialog.reject)
        row.addWidget(close)
        layout.addLayout(row)
        self.list_widget.currentItemChanged.connect(self._select)
        self.restore_button.clicked.connect(self._restore)
        self._diff = difflib.unified_diff
        self._message_box = QMessageBox
        self._qt_user_role = Qt.UserRole
        with open(manager.lifecycle.note_path(note_id), encoding='utf-8') as stream:
            self.current = json.load(stream)
        try:
            self.versions = manager.history_store.list_versions(self.current.get('note_uuid'))
        except (HistoryLockedError, ValueError) as exc:
            self.versions = []
            self.summary.setText(str(exc))
        else:
            used = manager.history_store.usage_bytes() / 1024 / 1024
            self.summary.setText(
                f'{len(self.versions)} 个本地版本；历史总占用 {used:.1f} MB；恢复前会保留当前内容'
                + (f'；{manager.history_store.last_warning}' if manager.history_store.last_warning else ''))
        for version in self.versions:
            label = version['created_at'].replace('T', ' ')[:19]
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, version['snapshot'])
            self.list_widget.addItem(item)

    def exec_(self):
        return self.dialog.exec_()

    def _select(self, item):
        self.restore_button.setEnabled(item is not None)
        if item is None:
            self.preview.clear()
            return
        version = next((value for value in self.versions
                        if value['snapshot'] == item.data(self._qt_user_role)), None)
        if version is None:
            self.preview.clear()
            return
        old = str(version['data'].get('plain_content', '')).splitlines()
        new = str(self.current.get('plain_content', '')).splitlines()
        lines = list(self._diff(new, old, fromfile='当前', tofile='选择的版本',
                                lineterm=''))
        self.preview.setPlainText('\n'.join(lines) or '正文无变化；可能修改了标题、清单、标签、提醒或附件。')

    def _restore(self):
        item = self.list_widget.currentItem()
        if item is None:
            return
        if self._message_box.question(
                self.dialog, '恢复版本', '恢复选中版本的内容？当前内容会先保留到历史。',
                self._message_box.Yes | self._message_box.No,
                self._message_box.No) != self._message_box.Yes:
            return
        try:
            self.manager.restore_note_history(self.note_id, item.data(self._qt_user_role))
        except Exception as exc:
            self._message_box.warning(self.dialog, '恢复失败', str(exc))
            return
        self.dialog.accept()

    def _clear(self):
        if self._message_box.question(
                self.dialog, '清理历史', '永久清除此便签的全部本地历史版本？',
                self._message_box.Yes | self._message_box.No,
                self._message_box.No) != self._message_box.Yes:
            return
        self.manager.history_store.remove_note(self.current.get('note_uuid'))
        self.versions = []
        self.list_widget.clear()
        self.summary.setText('此便签的本地历史已清理')

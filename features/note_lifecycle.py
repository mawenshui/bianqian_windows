# -*- coding: utf-8 -*-
"""便签归档与本地回收站。文件操作在服务层完成，窗口由管理器关闭。"""

import json
import hashlib
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from datetime import datetime


TRASH_NAME = re.compile(r'^note_(\d+)_([0-9a-f]{32})\.json$')


class NoteLifecycle:
    def __init__(self, notes_dir, trash_dir):
        self.notes_dir = os.path.realpath(notes_dir)
        self.trash_dir = os.path.realpath(trash_dir)
        os.makedirs(self.notes_dir, exist_ok=True)
        os.makedirs(self.trash_dir, exist_ok=True)

    def note_path(self, note_id):
        if not isinstance(note_id, int) or note_id < 1:
            raise ValueError('无效的便签 ID')
        return os.path.join(self.notes_dir, f'note_{note_id}.json')

    @staticmethod
    def _read(path):
        with open(path, encoding='utf-8') as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            raise ValueError('便签数据不是对象')
        return data

    @staticmethod
    def _write(path, data):
        descriptor, temporary = tempfile.mkstemp(
            prefix='.note_', suffix='.tmp', dir=os.path.dirname(path)
        )
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=4)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)

    def set_archived(self, note_id, archived):
        path = self.note_path(note_id)
        data = self._read(path)
        data['archived'] = bool(archived)
        self._write(path, data)
        return data

    def list_archive(self):
        items = []
        for name in os.listdir(self.notes_dir):
            match = re.fullmatch(r'note_(\d+)\.json', name)
            if not match:
                continue
            try:
                data = self._read(os.path.join(self.notes_dir, name))
                if data.get('archived'):
                    items.append({
                        'id': int(match.group(1)),
                        'title': data.get('title', '未命名便签'),
                        'locked': bool(data.get('locked')),
                    })
            except (OSError, ValueError, TypeError):
                continue
        return sorted(items, key=lambda item: str(item['title']).casefold())

    def move_to_trash(self, note_id):
        source = self.note_path(note_id)
        if not os.path.isfile(source):
            raise FileNotFoundError(source)
        data = self._read(source)
        data['trashed_at'] = datetime.now().isoformat(timespec='seconds')
        data['original_id'] = note_id
        attachment_source = os.path.join(self.notes_dir, 'attachments', f'note_{note_id}')
        image_source = self._managed_background(data, note_id, self.notes_dir)
        image_target = None
        if image_source and os.path.isfile(image_source):
            image_dir = os.path.join(self.trash_dir, 'images')
            os.makedirs(image_dir, exist_ok=True)
            image_name = f'{uuid.uuid4().hex}_{os.path.basename(image_source)}'
            image_target = os.path.join(image_dir, image_name)
            shutil.copy2(image_source, image_target)
            data['trash_background'] = image_name
        name = f'note_{note_id}_{uuid.uuid4().hex}.json'
        destination = os.path.join(self.trash_dir, name)
        attachment_target = os.path.join(self.trash_dir, 'attachments', name[:-5])
        if data.get('attachments') and not os.path.isdir(attachment_source):
            raise FileNotFoundError('便签附件目录缺失')
        if data.get('attachments'):
            from features.attachments import attachment_path
            for entry in data['attachments']:
                relative = entry.get('path', '') if isinstance(entry, dict) else ''
                if not relative.startswith(f'attachments/note_{note_id}/'):
                    raise ValueError('便签附件不属于当前便签')
                path = attachment_path(self.notes_dir, relative)
                if not os.path.isfile(path):
                    raise FileNotFoundError(f'便签附件缺失: {relative}')
        try:
            if os.path.isdir(attachment_source):
                os.makedirs(os.path.dirname(attachment_target), exist_ok=True)
                shutil.copytree(attachment_source, attachment_target)
                data['trash_attachments'] = name[:-5]
            # 完成目标写入后才移除源文件。
            self._write(destination, data)
            os.remove(source)
        except Exception:
            if os.path.exists(destination):
                os.remove(destination)
            if image_target and os.path.exists(image_target):
                os.remove(image_target)
            if os.path.isdir(attachment_target):
                shutil.rmtree(attachment_target)
            raise
        if os.path.isdir(attachment_target):
            try:
                shutil.rmtree(attachment_source)
            except OSError:
                pass
        if image_target:
            try:
                os.remove(image_source)
            except OSError:
                pass  # 保留旧图像副本，不影响回收站中的图像。
        return name

    @staticmethod
    def _managed_background(data, note_id, root):
        stored = data.get('background_image', '')
        if not isinstance(stored, str):
            return None
        normalized = stored.replace('\\', '/')
        if not re.fullmatch(rf'images/background_{note_id}_[^/\\]+', normalized):
            return None
        candidate = os.path.realpath(os.path.join(root, *normalized.split('/')))
        images_dir = os.path.realpath(os.path.join(root, 'images'))
        return candidate if os.path.commonpath([candidate, images_dir]) == images_dir else None

    def _trash_path(self, name):
        if not TRASH_NAME.fullmatch(name):
            raise ValueError('无效的回收站文件名')
        return os.path.join(self.trash_dir, name)

    def list_trash(self):
        items = []
        for name in os.listdir(self.trash_dir):
            if not TRASH_NAME.fullmatch(name):
                continue
            try:
                data = self._read(self._trash_path(name))
                items.append({
                    'name': name,
                    'title': data.get('title', '未命名便签'),
                    'deleted_at': data.get('trashed_at', ''),
                    'original_id': data.get('original_id'),
                    'locked': bool(data.get('locked')),
                })
            except (OSError, ValueError, TypeError):
                continue
        return sorted(items, key=lambda item: item['deleted_at'], reverse=True)

    def restore(self, name):
        source = self._trash_path(name)
        data = self._read(source)
        preferred = data.get('original_id')
        used = {
            int(match.group(1))
            for entry in os.listdir(self.notes_dir)
            if (match := re.fullmatch(r'note_(\d+)\.json', entry))
        }
        note_id = preferred if isinstance(preferred, int) and preferred > 0 else 1
        while note_id in used:
            note_id += 1
        data.pop('trashed_at', None)
        data.pop('original_id', None)
        image_name = data.pop('trash_background', None)
        attachment_name = data.pop('trash_attachments', None)
        attachment_source = None
        attachment_destination = None
        if attachment_name:
            if attachment_name != name[:-5]:
                raise ValueError('回收站附件目录不合法')
            attachment_source = os.path.join(self.trash_dir, 'attachments', attachment_name)
            if not os.path.isdir(attachment_source):
                raise FileNotFoundError('回收站附件目录缺失')
            attachment_destination = os.path.join(self.notes_dir, 'attachments', f'note_{note_id}')
            if os.path.exists(attachment_destination):
                raise FileExistsError('目标便签附件目录已存在')
            for entry in data.get('attachments', []):
                relative = entry.get('path', '')
                if not re.fullmatch(rf'attachments/note_{preferred}/[0-9a-f]{{32}}_[^/\\]+', relative):
                    raise ValueError('回收站附件路径不合法')
                if not os.path.isfile(os.path.join(attachment_source, relative.rsplit('/', 1)[-1])):
                    raise FileNotFoundError('回收站附件文件缺失')
                entry['path'] = relative.replace(f'attachments/note_{preferred}/',
                                                  f'attachments/note_{note_id}/', 1)
        image_source = None
        image_destination = None
        if image_name:
            if not re.fullmatch(r'[0-9a-f]{32}_background_\d+_[^/\\]+', image_name):
                raise ValueError('回收站图片路径不合法')
            image_source = os.path.join(self.trash_dir, 'images', image_name)
            if not os.path.isfile(image_source):
                raise FileNotFoundError('回收站中的便签背景图片缺失')
            original_basename = image_name.split('_', 1)[1]
            suffix = original_basename.split('_', 2)[2]
            new_basename = f'background_{note_id}_{suffix}'
            image_destination = os.path.join(self.notes_dir, 'images', new_basename)
            os.makedirs(os.path.dirname(image_destination), exist_ok=True)
            if os.path.exists(image_destination):
                new_basename = f'background_{note_id}_{uuid.uuid4().hex[:8]}_{suffix}'
                image_destination = os.path.join(self.notes_dir, 'images', new_basename)
            shutil.copy2(image_source, image_destination)
            data['background_image'] = f'images/{new_basename}'
        destination = self.note_path(note_id)
        try:
            if attachment_source:
                os.makedirs(os.path.dirname(attachment_destination), exist_ok=True)
                shutil.copytree(attachment_source, attachment_destination)
            self._write(destination, data)
            os.remove(source)
        except Exception:
            if os.path.exists(destination):
                os.remove(destination)
            if image_destination and os.path.exists(image_destination):
                os.remove(image_destination)
            if attachment_destination and os.path.isdir(attachment_destination):
                shutil.rmtree(attachment_destination)
            raise
        if attachment_source:
            try:
                shutil.rmtree(attachment_source)
            except OSError:
                pass
        if image_source:
            try:
                os.remove(image_source)
            except OSError:
                pass  # 恢复结果已落盘，残余回收站图像可稍后清理。
        return note_id

    def purge(self, name):
        """删除单条回收站记录及其专属资源。"""
        self.preview_purge([name])
        path = self._trash_path(name)
        data = self._read(path)
        os.remove(path)
        attachment_name = data.get('trash_attachments')
        if attachment_name == name[:-5]:
            folder = os.path.join(self.trash_dir, 'attachments', attachment_name)
            if os.path.isdir(folder):
                shutil.rmtree(folder)
        image_name = data.get('trash_background')
        if isinstance(image_name, str) and re.fullmatch(
            r'[0-9a-f]{32}_background_\d+_[^/\\]+', image_name
        ):
            image_path = os.path.join(self.trash_dir, 'images', image_name)
            if os.path.isfile(image_path):
                os.remove(image_path)

    def preview_purge(self, names):
        """只读统计永久删除影响，拒绝无效条目和链接。"""
        report = {'notes': 0, 'attachments': 0, 'attachment_bytes': 0,
                  'backgrounds': 0, 'background_bytes': 0, 'names': []}
        for name in dict.fromkeys(names):
            data = self._read(self._trash_path(name))
            report['notes'] += 1
            report['names'].append(name)
            folder_name = data.get('trash_attachments')
            if folder_name:
                if folder_name != name[:-5]:
                    raise ValueError(f'回收站附件归属不一致: {name}')
                folder = os.path.join(self.trash_dir, 'attachments', folder_name)
                if os.path.islink(folder):
                    raise ValueError('不允许清理链接附件目录')
                if os.path.isdir(folder):
                    for filename in os.listdir(folder):
                        path = os.path.join(folder, filename)
                        if os.path.islink(path) or not os.path.isfile(path):
                            raise ValueError(f'附件不是普通文件: {filename}')
                        report['attachments'] += 1
                        report['attachment_bytes'] += os.path.getsize(path)
            image_name = data.get('trash_background')
            if isinstance(image_name, str) and re.fullmatch(
                r'[0-9a-f]{32}_background_\d+_[^/\\]+', image_name
            ):
                path = os.path.join(self.trash_dir, 'images', image_name)
                if os.path.islink(path):
                    raise ValueError('不允许清理链接背景图')
                if os.path.isfile(path):
                    report['backgrounds'] += 1
                    report['background_bytes'] += os.path.getsize(path)
        return report

    def preview_cleanup(self, retention_days):
        """只读列出超过保留期限的便签及资源。"""
        if retention_days <= 0:
            return self.preview_purge([])
        cutoff = time.time() - retention_days * 86400
        names = [item['name'] for item in self.list_trash()
                 if os.path.getmtime(self._trash_path(item['name'])) < cutoff]
        return self.preview_purge(names)

    def scan_orphan_attachments(self):
        """查找没有被便签 JSON 引用的托管附件。"""
        orphaned = []
        for root, pattern in ((self.notes_dir, r'note_\d+'),
                              (self.trash_dir, r'note_\d+_[0-9a-f]{32}')):
            attachment_root = os.path.join(root, 'attachments')
            if not os.path.isdir(attachment_root) or os.path.islink(attachment_root):
                continue
            for folder in os.listdir(attachment_root):
                if not re.fullmatch(pattern, folder):
                    continue
                directory = os.path.join(attachment_root, folder)
                if not os.path.isdir(directory) or os.path.islink(directory):
                    continue
                note_path = os.path.join(root, folder + '.json')
                data = self._read(note_path) if os.path.isfile(note_path) else {}
                referenced = {
                    entry['path'].rsplit('/', 1)[-1]
                    for entry in data.get('attachments', [])
                    if isinstance(entry, dict) and isinstance(entry.get('path'), str)
                }
                for filename in os.listdir(directory):
                    path = os.path.join(directory, filename)
                    if (re.fullmatch(r'[0-9a-f]{32}_[^/\\]+', filename)
                            and os.path.isfile(path) and not os.path.islink(path)
                            and filename not in referenced):
                        orphaned.append({'path': path, 'bytes': os.path.getsize(path)})
        return orphaned

    def remove_orphan_attachments(self):
        """重新扫描后仅删除仍未被引用的普通文件。"""
        orphaned = self.scan_orphan_attachments()
        for entry in orphaned:
            os.remove(entry['path'])
        return len(orphaned)

    def archive_and_remove_orphans(self, backup_dir):
        """先独立归档并校验孤立文件，再逐个删除；归档始终保留。"""
        orphaned = self.scan_orphan_attachments()
        if not orphaned:
            return 0, None
        os.makedirs(backup_dir, exist_ok=True)
        archive_path = os.path.join(
            backup_dir, f'orphan_attachments_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}.zip'
        )
        expected = {}
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for entry in orphaned:
                root = self.notes_dir if os.path.commonpath([entry['path'], self.notes_dir]) == self.notes_dir else self.trash_dir
                folder = 'notes' if root == self.notes_dir else 'trash'
                member = f'{folder}/{os.path.relpath(entry["path"], root).replace(os.sep, "/")}'
                with open(entry['path'], 'rb') as stream:
                    payload = stream.read()
                expected[member] = hashlib.sha256(payload).hexdigest()
                archive.writestr(member, payload)
            archive.writestr('SHA256.json', json.dumps(expected, ensure_ascii=False))
        with zipfile.ZipFile(archive_path) as archive:
            if archive.testzip() or any(hashlib.sha256(archive.read(name)).hexdigest() != digest
                                        for name, digest in expected.items()):
                raise RuntimeError('孤立附件归档校验失败，未清理')
        current = {entry['path'] for entry in self.scan_orphan_attachments()}
        removed = 0
        for entry in orphaned:
            if entry['path'] in current:
                root = self.notes_dir if os.path.commonpath([entry['path'], self.notes_dir]) == self.notes_dir else self.trash_dir
                folder = 'notes' if root == self.notes_dir else 'trash'
                member = f'{folder}/{os.path.relpath(entry["path"], root).replace(os.sep, "/")}'
                with open(entry['path'], 'rb') as stream:
                    if hashlib.sha256(stream.read()).hexdigest() != expected[member]:
                        continue  # 归档之后内容变化，保留文件等待下次检查。
                os.remove(entry['path'])
                removed += 1
        return removed, archive_path

    def cleanup(self, retention_days, safety_backup=None):
        if retention_days <= 0:
            return 0  # 0 表示永久保留，直到用户手动清空。
        report = self.preview_cleanup(retention_days)
        if report['notes'] and safety_backup is not None and not safety_backup():
            raise RuntimeError('自动清理前安全备份失败，回收站未修改')
        for name in report['names']:
            self.purge(name)
        return report['notes']


class NoteLifecycleDialog:
    """延迟创建 Qt 对话框，避免数据服务依赖图形界面。"""

    @staticmethod
    def show(manager, parent=None):
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
            QListWidgetItem, QPushButton, QMessageBox, QSpinBox, QTabWidget,
            QWidget,
        )

        dialog = QDialog(parent)
        dialog.setWindowTitle('归档与回收站')
        dialog.resize(560, 480)
        layout = QVBoxLayout(dialog)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        archive_page = QWidget()
        archive_layout = QVBoxLayout(archive_page)
        archive_list = QListWidget()
        archive_list.setAccessibleName('归档便签列表')
        archive_list.setSelectionMode(QListWidget.ExtendedSelection)
        archive_layout.addWidget(archive_list)
        archive_actions = QHBoxLayout()
        unarchive_button = QPushButton('取消归档并打开')
        archive_actions.addWidget(unarchive_button)
        archive_layout.addLayout(archive_actions)
        tabs.addTab(archive_page, '归档')

        trash_page = QWidget()
        trash_layout = QVBoxLayout(trash_page)
        trash_list = QListWidget()
        trash_list.setAccessibleName('回收站便签列表')
        trash_list.setSelectionMode(QListWidget.ExtendedSelection)
        trash_layout.addWidget(trash_list)
        trash_actions = QHBoxLayout()
        restore_button = QPushButton('恢复选中')
        purge_button = QPushButton('永久删除选中')
        orphan_button = QPushButton('检查孤立附件')
        trash_actions.addWidget(restore_button)
        trash_actions.addWidget(purge_button)
        trash_actions.addWidget(orphan_button)
        trash_layout.addLayout(trash_actions)
        retention = QSpinBox()
        retention.setAccessibleName('回收站保留天数')
        retention.setRange(0, 3650)
        retention.setSuffix(' 天（0 为永久保留）')
        retention.setValue(manager.config.get('trash_retention_days', 30))
        trash_layout.addWidget(QLabel('回收站保留期限：'))
        trash_layout.addWidget(retention)
        tabs.addTab(trash_page, '回收站')

        def refresh():
            archive_list.clear()
            for entry in manager.lifecycle.list_archive():
                item = QListWidgetItem(
                    f"{entry['title']} (ID {entry['id']})" +
                    (' · 已锁定' if entry['locked'] else '')
                )
                item.setData(Qt.UserRole, entry['id'])
                archive_list.addItem(item)
            trash_list.clear()
            for entry in manager.lifecycle.list_trash():
                item = QListWidgetItem(
                    f"{entry['title']} · {entry['deleted_at']}" +
                    (' · 已锁定' if entry['locked'] else '')
                )
                item.setData(Qt.UserRole, entry['name'])
                trash_list.addItem(item)

        def unarchive():
            for item in archive_list.selectedItems():
                manager.unarchive_note(item.data(Qt.UserRole))
            refresh()

        def restore():
            for item in trash_list.selectedItems():
                try:
                    manager.restore_trashed_note(item.data(Qt.UserRole))
                except Exception as exc:
                    QMessageBox.warning(dialog, '恢复失败', str(exc))
            refresh()

        def purge():
            items = trash_list.selectedItems()
            if not items:
                return
            names = [item.data(Qt.UserRole) for item in items]
            try:
                impact = manager.lifecycle.preview_purge(names)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(dialog, '无法预览删除', str(exc))
                return
            if QMessageBox.question(
                dialog, '永久删除',
                f'将永久删除 {impact["notes"]} 个便签、{impact["attachments"]} 个附件'
                f'（{impact["attachment_bytes"] / 1024 / 1024:.1f} MB）和 '
                f'{impact["backgrounds"]} 张背景图。清理前会创建安全备份。',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) != QMessageBox.Yes:
                return
            snapshot = manager.backup_manager.create_backup()
            if not snapshot or not manager.backup_manager.preview_backup(snapshot)['valid']:
                QMessageBox.warning(dialog, '删除已取消', '安全备份失败，回收站未修改。')
                return
            for name in names:
                try:
                    manager.lifecycle.purge(name)
                except (OSError, ValueError) as exc:
                    QMessageBox.warning(dialog, '删除未完成', f'{name}: {exc}')
                    break
            refresh()
            QMessageBox.information(dialog, '删除完成', f'安全备份：\n{snapshot}')

        def inspect_orphans():
            try:
                entries = manager.lifecycle.scan_orphan_attachments()
                total = sum(entry['bytes'] for entry in entries)
                if not entries:
                    QMessageBox.information(dialog, '孤立附件检查', '未发现孤立附件。')
                    return
                detail = '\n'.join(os.path.basename(entry['path']) for entry in entries[:8])
                if QMessageBox.question(
                    dialog, '孤立附件检查',
                    f'发现 {len(entries)} 个未被便签引用的附件，共 {total / 1024 / 1024:.1f} MB。'
                    f'\n预览：\n{detail}\n\n创建安全备份后清理？',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                ) != QMessageBox.Yes:
                    return
                removed, snapshot = manager.lifecycle.archive_and_remove_orphans(
                    manager.backup_manager.backup_dir)
                QMessageBox.information(dialog, '清理完成',
                                        f'清理 {removed} 个孤立附件。安全备份：\n{snapshot}')
            except (OSError, ValueError, RuntimeError) as exc:
                QMessageBox.warning(dialog, '孤立附件检查失败', str(exc))

        def save_retention(value):
            previous = manager.config.get('trash_retention_days', 30)
            try:
                impact = manager.lifecycle.preview_cleanup(value)
                if impact['notes'] and QMessageBox.question(
                    dialog, '到期清理预览',
                    f'将清理 {impact["notes"]} 个便签、{impact["attachments"]} 个附件'
                    f'（{impact["attachment_bytes"] / 1024 / 1024:.1f} MB）。'
                    '清理前会创建安全备份。继续吗？',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                ) != QMessageBox.Yes:
                    retention.blockSignals(True)
                    retention.setValue(previous)
                    retention.blockSignals(False)
                    return
                if impact['notes'] and manager.cleanup_trash(value) != impact['notes']:
                    raise RuntimeError('清理未完成，保留期限未修改')
            except (OSError, ValueError, RuntimeError) as exc:
                QMessageBox.warning(dialog, '到期清理失败', str(exc))
                retention.blockSignals(True)
                retention.setValue(previous)
                retention.blockSignals(False)
                return
            manager.config.set('trash_retention_days', value)
            refresh()

        unarchive_button.clicked.connect(unarchive)
        restore_button.clicked.connect(restore)
        purge_button.clicked.connect(purge)
        orphan_button.clicked.connect(inspect_orphans)
        retention.valueChanged.connect(save_retention)
        refresh()
        dialog.exec_()

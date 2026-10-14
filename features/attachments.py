# -*- coding: utf-8 -*-
"""便签本地附件。JSON 中只保存相对路径，文件始终留在用户数据目录。"""

import os
import re
import shutil
import uuid


def attachment_path(root, relative):
    if not isinstance(relative, str) or not re.fullmatch(
        r'attachments/note_\d+/[0-9a-f]{32}_[^/\\]+', relative
    ):
        raise ValueError('无效的附件路径')
    path = os.path.realpath(os.path.join(root, *relative.split('/')))
    base = os.path.realpath(os.path.join(root, 'attachments'))
    if os.path.commonpath([path, base]) != base:
        raise ValueError('附件超出数据目录')
    return path


def add_attachment(notes_dir, note_id, source):
    if not os.path.isfile(source):
        raise FileNotFoundError(source)
    if os.path.getsize(source) > 50 * 1024 * 1024:
        raise ValueError('单个附件不能超过 50 MB')
    name = os.path.basename(source)
    if not name or name in ('.', '..'):
        raise ValueError('附件文件名无效')
    safe = re.sub(r'[^\w.()-]', '_', name, flags=re.UNICODE)[:100]
    relative = f'attachments/note_{note_id}/{uuid.uuid4().hex}_{safe}'
    destination = attachment_path(notes_dir, relative)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copy2(source, destination)
    return {'name': name, 'path': relative}


def remove_attachment(notes_dir, entry):
    path = attachment_path(notes_dir, entry['path'])
    if os.path.isfile(path):
        os.remove(path)

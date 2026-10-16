# -*- coding: utf-8 -*-
"""Crash-resilient visibility overlay for intentional presentation hiding."""

import json
import os

from features.note_history import _atomic_bytes


class PresentationState:
    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, 'presentation_state.json')

    def read(self):
        if not os.path.isfile(self.path):
            return {'active': False, 'notes': {}}
        with open(self.path, encoding='utf-8') as stream:
            state = json.load(stream)
        if not isinstance(state, dict) or not isinstance(state.get('notes'), dict):
            raise ValueError('演示遮蔽状态文件无效')
        return {'active': bool(state.get('active')), 'notes': state['notes']}

    def write(self, active, notes):
        _atomic_bytes(self.path, json.dumps(
            {'active': bool(active), 'notes': notes},
            ensure_ascii=False, separators=(',', ':')).encode('utf-8'))

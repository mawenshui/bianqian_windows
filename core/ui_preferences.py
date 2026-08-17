# -*- coding: utf-8 -*-
"""Shared, validation-first preferences for the desktop UI."""

from typing import Iterable, List


SETTINGS_TOOL_ORDER_KEY = 'ui.settings_tool_order'

# Left-to-right order for the note's settings rail.  The three daily controls
# deliberately lead the row; image-specific controls remain available after
# them without competing for the first scan position.
DEFAULT_SETTINGS_TOOL_ORDER = (
    'window_opacity',
    'behaviour',
    'control_opacity',
    'background',
    'background_colors',
)

SETTINGS_TOOL_LABELS = {
    'window_opacity': '便签透明度',
    'behaviour': '总在最前与智能格式化',
    'control_opacity': '控件透明度',
    'background': '背景图片',
    'background_colors': '背景文字与控件颜色',
}


def normalize_settings_tool_order(value: Iterable[str] = None) -> List[str]:
    """Return a complete, duplicate-free order safe for layouts/config files."""
    if isinstance(value, str):
        candidates = [part.strip() for part in value.split(',')]
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        candidates = []

    result = []
    for candidate in candidates:
        key = str(candidate).strip()
        if key in SETTINGS_TOOL_LABELS and key not in result:
            result.append(key)
    for key in DEFAULT_SETTINGS_TOOL_ORDER:
        if key not in result:
            result.append(key)
    return result

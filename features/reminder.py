# -*- coding: utf-8 -*-
"""
定时提醒功能模块

提供便签定时提醒功能，支持：
- 一次性提醒（指定日期时间）
- 周期提醒（每天/每周/每月）
- 到期时系统托盘通知
- 提醒数据持久化到 note JSON 中
"""

from datetime import datetime, timedelta
from enum import Enum

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QComboBox, QCheckBox, QPushButton, QLabel,
    QDateTimeEdit, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QDateTime


class RepeatMode(Enum):
    """提醒重复模式"""
    ONCE = "once"       # 一次性
    DAILY = "daily"     # 每天
    WEEKLY = "weekly"   # 每周
    MONTHLY = "monthly" # 每月


class ReminderData:
    """提醒数据模型"""

    def __init__(self, data: dict = None):
        d = data or {}
        self.enabled: bool = d.get('enabled', False)
        self.datetime_str: str = d.get('datetime', '')          # ISO 格式
        self.repeat: str = d.get('repeat', RepeatMode.ONCE.value)
        self.message: str = d.get('message', '')
        self.last_triggered: str = d.get('last_triggered', '')  # ISO 格式（防重复触发）

    def to_dict(self) -> dict:
        return {
            'enabled': self.enabled,
            'datetime': self.datetime_str,
            'repeat': self.repeat,
            'message': self.message,
            'last_triggered': self.last_triggered,
        }

    def is_due(self) -> bool:
        """判断提醒是否已到期"""
        if not self.enabled or not self.datetime_str:
            return False
        try:
            target = datetime.fromisoformat(self.datetime_str)
            now = datetime.now()

            if self.repeat == RepeatMode.ONCE.value:
                # 一次性：当前时间 > 目标时间 且 今天还没触发过
                if now < target:
                    return False
                return self.last_triggered != now.strftime('%Y-%m-%d')
            elif self.repeat == RepeatMode.DAILY.value:
                # 每天：今天的目标时间未触发
                today_target = now.replace(hour=target.hour, minute=target.minute, second=0)
                if now < today_target:
                    return False
                return self.last_triggered != now.strftime('%Y-%m-%d')
            elif self.repeat == RepeatMode.WEEKLY.value:
                # 每周：本周该星期几的目标时间
                today_target = now.replace(hour=target.hour, minute=target.minute, second=0)
                day_diff = target.weekday() - now.weekday()
                if day_diff > 0 or (day_diff == 0 and now < today_target):
                    return False
                if day_diff == 0:
                    return self.last_triggered != now.strftime('%Y-%m-%d')
                # 目标星期已过，但还没触发
                return self.last_triggered != now.strftime('%Y-%m-%d')
            elif self.repeat == RepeatMode.MONTHLY.value:
                today_target = now.replace(
                    day=min(target.day, 28),
                    hour=target.hour, minute=target.minute, second=0
                )
                if now < today_target:
                    return False
                return self.last_triggered != now.strftime('%Y-%m-%d')
        except (ValueError, OSError):
            return False
        return False

    def mark_triggered(self):
        """标记已触发"""
        self.last_triggered = datetime.now().strftime('%Y-%m-%d')


class ReminderDialog(QDialog):
    """提醒设置对话框"""

    def __init__(self, note, parent=None):
        super().__init__(parent)
        self.note = note
        self.reminder = ReminderData(note.note_data.get('reminder'))
        self.initUI()
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        # 应用主题适配
        try:
            from features.theme_helper import apply_dialog_theme, get_current_theme_css
            manager = getattr(note, 'manager', None)
            apply_dialog_theme(self, get_current_theme_css(manager))
        except Exception:
            pass

    def initUI(self):
        self.setWindowTitle('\u63d0\u9192\u8bbe\u7f6e')
        self.setFixedSize(420, 350)

        layout = QVBoxLayout()

        # 启用开关
        self.enabled_check = QCheckBox('\u542f\u7528\u5b9a\u65f6\u63d0\u9192')
        self.enabled_check.setChecked(self.reminder.enabled)
        layout.addWidget(self.enabled_check)

        # 日期时间
        dt_group = QGroupBox('\u63d0\u9192\u65f6\u95f4')
        dt_layout = QFormLayout()

        self.datetime_edit = QDateTimeEdit()
        self.datetime_edit.setCalendarPopup(True)
        self.datetime_edit.setDisplayFormat('yyyy-MM-dd HH:mm')
        if self.reminder.datetime_str:
            self.datetime_edit.setDateTime(
                QDateTime.fromString(self.reminder.datetime_str, 'yyyy-MM-ddTHH:mm')
            )
        else:
            self.datetime_edit.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        dt_layout.addRow('\u65e5\u671f\u65f6\u95f4:', self.datetime_edit)

        # 重复模式
        self.repeat_combo = QComboBox()
        self.repeat_combo.addItems([
            '\u4e00\u6b21\u6027', '\u6bcf\u5929', '\u6bcf\u5468', '\u6bcf\u6708'
        ])
        repeat_map = {
            RepeatMode.ONCE.value: 0, RepeatMode.DAILY.value: 1,
            RepeatMode.WEEKLY.value: 2, RepeatMode.MONTHLY.value: 3
        }
        self.repeat_combo.setCurrentIndex(repeat_map.get(self.reminder.repeat, 0))
        dt_layout.addRow('\u91cd\u590d\u6a21\u5f0f:', self.repeat_combo)

        dt_group.setLayout(dt_layout)
        layout.addWidget(dt_group)

        # 提醒消息
        msg_group = QGroupBox('\u63d0\u9192\u6d88\u606f')
        msg_layout = QVBoxLayout()
        self.message_label = QLabel(
            self.reminder.message or '\u5f53\u524d\u4fbf\u7b7e\u5185\u5bb9\u5c06\u4f5c\u4e3a\u63d0\u9192\u6d88\u606f'
        )
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet('color: gray; font-size: 10pt;')
        msg_layout.addWidget(self.message_label)
        msg_group.setLayout(msg_layout)
        layout.addWidget(msg_group)

        layout.addStretch()

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton('\u4fdd\u5b58')
        save_btn.setFixedSize(80, 32)
        save_btn.clicked.connect(self.save_reminder)
        cancel_btn = QPushButton('\u53d6\u6d88')
        cancel_btn.setFixedSize(80, 32)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def save_reminder(self):
        self.reminder.enabled = self.enabled_check.isChecked()
        self.reminder.datetime_str = self.datetime_edit.dateTime().toString('yyyy-MM-ddTHH:mm')
        mode_map = {0: RepeatMode.ONCE.value, 1: RepeatMode.DAILY.value,
                     2: RepeatMode.WEEKLY.value, 3: RepeatMode.MONTHLY.value}
        self.reminder.repeat = mode_map[self.repeat_combo.currentIndex()]
        self.reminder.message = self.note.title_edit.text().strip()

        self.note.note_data['reminder'] = self.reminder.to_dict()
        if not self.note.is_deleted:
            self.note.save_note()
        self.accept()


class ReminderManager:
    """
    提醒管理器

    定时轮询所有便签的提醒状态，到期时通过系统托盘发出通知。
    """

    def __init__(self, manager):
        self.manager = manager
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_reminders)
        self.timer.start(30000)  # 每 30 秒检查一次

    def check_reminders(self):
        """检查所有便签是否有到期的提醒"""
        for note in list(self.manager.notes.values()):
            if note.is_deleted:
                continue
            reminder_data = note.note_data.get('reminder')
            if not reminder_data:
                continue
            reminder = ReminderData(reminder_data)
            if reminder.is_due():
                self._trigger_reminder(note, reminder)

    def _trigger_reminder(self, note, reminder: ReminderData):
        """触发提醒通知"""
        title = note.note_data.get('title', f'\u4fbf\u7b7e {note.note_id}')
        content = note.text_edit.toPlainText()
        # 截断内容作为通知消息
        msg = reminder.message or (
            content[:100] + '...' if len(content) > 100 else content
        )
        self.manager.tray_icon.showMessage(
            f'\u23f0 {title}',
            msg,
            self.manager.tray_icon.Information,
            5000
        )
        # 标记已触发，防止重复通知
        reminder.mark_triggered()
        note.note_data['reminder'] = reminder.to_dict()
        if not note.is_deleted:
            note.save_note()

    def get_reminder_info(self, note) -> dict:
        """获取便签的提醒状态信息（供 UI 显示）"""
        data = note.note_data.get('reminder')
        if not data:
            return {'enabled': False, 'text': ''}
        r = ReminderData(data)
        if not r.enabled:
            return {'enabled': False, 'text': ''}
        repeat_label = {
            RepeatMode.ONCE.value: '',
            RepeatMode.DAILY.value: ' \u6bcf\u5929',
            RepeatMode.WEEKLY.value: ' \u6bcf\u5468',
            RepeatMode.MONTHLY.value: ' \u6bcf\u6708',
        }.get(r.repeat, '')
        try:
            dt = datetime.fromisoformat(r.datetime_str)
            time_str = dt.strftime('%m-%d %H:%M')
        except (ValueError, OSError):
            time_str = r.datetime_str
        return {
            'enabled': True,
            'text': f'\u23f0 {time_str}{repeat_label}'
        }

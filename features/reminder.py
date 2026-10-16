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
import calendar
import copy
import time
from enum import Enum

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QComboBox, QCheckBox, QPushButton, QLabel,
    QDateTimeEdit, QMessageBox, QListWidget, QListWidgetItem, QInputDialog
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
        self.completed: bool = bool(d.get('completed', False))
        self.snoozed_until: str = d.get('snoozed_until', '')

    def to_dict(self) -> dict:
        return {
            'enabled': self.enabled,
            'datetime': self.datetime_str,
            'repeat': self.repeat,
            'message': self.message,
            'last_triggered': self.last_triggered,
            'completed': self.completed,
            'snoozed_until': self.snoozed_until,
        }

    def is_due(self, now=None) -> bool:
        """判断提醒是否已到期"""
        if not self.enabled or self.completed or not self.datetime_str:
            return False
        try:
            target = datetime.fromisoformat(self.datetime_str)
            now = now or datetime.now()
            if self.snoozed_until:
                return now >= datetime.fromisoformat(self.snoozed_until)
            if self.repeat == RepeatMode.ONCE.value:
                return now >= target and not self.last_triggered
            occurrence = self._occurrence(target, now)
            return now >= occurrence >= target and self.last_triggered != occurrence.date().isoformat()
        except (ValueError, OSError, TypeError):
            return False

    def _occurrence(self, target, now):
        if self.repeat == RepeatMode.DAILY.value:
            occurrence = now.replace(hour=target.hour, minute=target.minute,
                                     second=0, microsecond=0)
            return occurrence - timedelta(days=1) if occurrence > now else occurrence
        if self.repeat == RepeatMode.WEEKLY.value:
            day = now.date() - timedelta(days=(now.weekday() - target.weekday()) % 7)
            occurrence = datetime.combine(day, target.time()).replace(second=0, microsecond=0)
            return occurrence - timedelta(days=7) if occurrence > now else occurrence
        if self.repeat == RepeatMode.MONTHLY.value:
            day = min(target.day, calendar.monthrange(now.year, now.month)[1])
            occurrence = now.replace(day=day, hour=target.hour, minute=target.minute,
                                     second=0, microsecond=0)
            if occurrence > now:
                year, month = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
                day = min(target.day, calendar.monthrange(year, month)[1])
                occurrence = occurrence.replace(year=year, month=month, day=day)
            return occurrence
        return target

    def mark_triggered(self):
        """标记已触发"""
        now = datetime.now()
        target = datetime.fromisoformat(self.datetime_str)
        occurrence = target if self.repeat == RepeatMode.ONCE.value else self._occurrence(target, now)
        self.last_triggered = occurrence.date().isoformat()
        self.snoozed_until = ''


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
        self.reminder.completed = False
        self.reminder.last_triggered = ''
        self.reminder.snoozed_until = ''

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
        self._undo = []
        self.last_check_reason = '启动检查'
        self.last_check_at = None
        self._last_wall = datetime.now()
        self._last_monotonic = time.monotonic()
        self._last_offset = datetime.now().astimezone().utcoffset()
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_reminders)
        self.timer.start(30000)  # 每 30 秒检查一次
        QTimer.singleShot(0, self.check_reminders)

    def check_reminders(self):
        """检查所有便签是否有到期的提醒"""
        now = datetime.now()
        monotonic = time.monotonic()
        offset = now.astimezone().utcoffset()
        wall_elapsed = (now - self._last_wall).total_seconds()
        elapsed = monotonic - self._last_monotonic
        if offset != self._last_offset:
            self.last_check_reason = '时区变化检查'
        elif wall_elapsed - elapsed > 60:
            self.last_check_reason = '唤醒或时钟变化检查'
        elif self.last_check_at is None:
            self.last_check_reason = '启动补触发检查'
        else:
            self.last_check_reason = '定时检查'
        self.last_check_at = now
        self._last_wall, self._last_monotonic, self._last_offset = now, monotonic, offset
        for note in list(self.manager.notes.values()):
            if getattr(note, 'is_deleted', False):
                continue
            reminder_data = note.note_data.get('reminder')
            if not reminder_data:
                continue
            reminder = ReminderData(reminder_data)
            if reminder.is_due(now):
                self._trigger_reminder(note, reminder)

    @staticmethod
    def _persist(note):
        if getattr(note, 'is_deleted', False):
            return
        save_sync = getattr(note, 'save_note_sync', None)
        if callable(save_sync):
            save_sync()
        else:
            note.save_note()

    def list_entries(self):
        entries = []
        for note_id, note in self.manager.notes.items():
            data = note.note_data.get('reminder')
            if not isinstance(data, dict) or not data.get('datetime'):
                continue
            reminder = ReminderData(data)
            if not reminder.enabled and not reminder.completed:
                continue
            state = ('已完成' if reminder.completed else
                     '已通知' if reminder.repeat == 'once' and reminder.last_triggered and not reminder.snoozed_until else
                     '已到期' if reminder.is_due() else
                     '未触发' if reminder.snoozed_until else
                     '等待下次周期' if reminder.repeat != 'once' and reminder.last_triggered else
                     '未触发')
            entries.append((note_id, note.note_data.get('title', f'便签 {note_id}'), state,
                            reminder.datetime_str))
        return sorted(entries, key=lambda entry: entry[3])

    def snooze(self, note_id, minutes=10):
        note = self.manager.notes[note_id]
        self._remember(note_id, note)
        reminder = ReminderData(note.note_data.get('reminder'))
        reminder.enabled = True
        reminder.completed = False
        reminder.snoozed_until = (datetime.now() + timedelta(minutes=minutes)).isoformat(timespec='minutes')
        note.note_data['reminder'] = reminder.to_dict()
        self._persist(note)

    def complete(self, note_id):
        note = self.manager.notes[note_id]
        self._remember(note_id, note)
        reminder = ReminderData(note.note_data.get('reminder'))
        reminder.completed = True
        reminder.enabled = False
        note.note_data['reminder'] = reminder.to_dict()
        self._persist(note)

    def _remember(self, note_id, note):
        self._undo.append((note_id, copy.deepcopy(note.note_data.get('reminder'))))
        self._undo = self._undo[-20:]

    def undo_last_action(self):
        """仅撤销本次运行中最近一次稍后提醒或完成操作。"""
        if not self._undo:
            return False
        note_id, previous = self._undo.pop()
        note = self.manager.notes.get(note_id)
        if note is None or getattr(note, 'is_deleted', False):
            return False
        if previous is None:
            note.note_data.pop('reminder', None)
        else:
            note.note_data['reminder'] = previous
        self._persist(note)
        return True

    def _trigger_reminder(self, note, reminder: ReminderData):
        """触发提醒通知"""
        title = note.note_data.get('title', f'\u4fbf\u7b7e {note.note_id}')
        content = note.text_edit.toPlainText()
        # 截断内容作为通知消息
        msg = reminder.message or (
            content[:100] + '...' if len(content) > 100 else content
        )
        # 标记已触发，防止重复通知
        reminder.mark_triggered()
        note.note_data['reminder'] = reminder.to_dict()
        self._persist(note)
        if getattr(self.manager, 'presentation_active', False):
            return
        self.manager.tray_icon.showMessage(
            f'\u23f0 {title}', msg, self.manager.tray_icon.Information, 5000
        )

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


class ReminderCenterDialog(QDialog):
    """本地提醒总览。"""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle('提醒中心')
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        self.filter = QComboBox()
        self.filter.addItems(['全部', '未触发', '已到期', '已通知', '等待下次周期', '已完成'])
        self.filter.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.filter)
        self.check_status = QLabel()
        self.check_status.setAccessibleName('最近提醒检查状态')
        layout.addWidget(self.check_status)
        self.listing = QListWidget()
        self.listing.setAccessibleName('提醒列表')
        layout.addWidget(self.listing)
        row = QHBoxLayout()
        open_button = QPushButton('打开便签')
        snooze_button = QPushButton('稍后提醒')
        done_button = QPushButton('标记完成')
        undo_button = QPushButton('撤销上次操作')
        refresh_button = QPushButton('刷新')
        for button in (open_button, snooze_button, done_button, undo_button, refresh_button):
            row.addWidget(button)
        layout.addLayout(row)
        open_button.clicked.connect(self.open_selected)
        snooze_button.clicked.connect(self.snooze_selected)
        done_button.clicked.connect(self.complete_selected)
        undo_button.clicked.connect(self.undo_action)
        refresh_button.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self):
        reminder_manager = self.manager.reminder_manager
        checked = getattr(reminder_manager, 'last_check_at', None)
        self.check_status.setText(
            f'最近检查：{checked:%Y-%m-%d %H:%M:%S} · {reminder_manager.last_check_reason}'
            if checked else '等待启动检查'
        )
        self.listing.clear()
        state_filter = self.filter.currentText()
        for note_id, title, state, when in self.manager.reminder_manager.list_entries():
            if state_filter != '全部' and state_filter != state:
                continue
            note = self.manager.notes.get(note_id)
            reminder = note.note_data.get('reminder', {}) if note else {}
            detail = (' · 已稍后提醒至 ' + reminder['snoozed_until']
                      if state == '未触发' and isinstance(reminder, dict)
                      and reminder.get('snoozed_until') else '')
            item = QListWidgetItem(f'{state}{detail} · {when} · {title}')
            item.setData(Qt.UserRole, note_id)
            self.listing.addItem(item)

    def _selected_id(self):
        item = self.listing.currentItem()
        return item.data(Qt.UserRole) if item else None

    def open_selected(self):
        note_id = self._selected_id()
        if note_id is not None:
            self.manager.open_note(note_id)

    def snooze_selected(self):
        note_id = self._selected_id()
        if note_id is None:
            return
        minutes, ok = QInputDialog.getInt(self, '稍后提醒', '分钟:', 10, 1, 1440)
        if ok:
            self.manager.reminder_manager.snooze(note_id, minutes)
            self.refresh()

    def complete_selected(self):
        note_id = self._selected_id()
        if note_id is not None:
            self.manager.reminder_manager.complete(note_id)
            self.refresh()

    def undo_action(self):
        if not self.manager.reminder_manager.undo_last_action():
            QMessageBox.information(self, '撤销提醒操作', '本次运行中没有可撤销的操作。')
        self.refresh()

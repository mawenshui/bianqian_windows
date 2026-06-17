# -*- coding: utf-8 -*-
"""
番茄计时器插件

可自定义工作和休息时间的番茄工作法计时器。
"""

from PyQt5.QtCore import QTimer
from features.plugin_system.base import PluginBase


class PomodoroPlugin(PluginBase):
    """番茄计时器插件"""

    name = '番茄计时器'
    version = '1.1.0'
    author = 'StickyNote'
    description = '可自定义时间的番茄工作法计时器'

    def on_load(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._remaining = 0
        self._is_working = True
        self._work_minutes = self.config.get('work_minutes', 25)
        self._break_minutes = self.config.get('break_minutes', 5)
        self._long_break_minutes = self.config.get('long_break_minutes', 15)
        self._rounds_before_long_break = self.config.get('rounds_before_long_break', 4)
        self._current_round = 0

        self.register_tray_menu_item('🍅 开始番茄钟', self.start_pomodoro)
        self.register_tray_menu_item('⏹ 停止番茄钟', self.stop_pomodoro)

    def on_unload(self):
        self._timer.stop()

    def get_config_fields(self):
        return [
            {
                'key': 'work_minutes',
                'label': '工作时长',
                'type': 'int',
                'default': 25,
                'min': 1,
                'max': 120,
                'suffix': '分钟',
                'help': '每轮专注工作的时间',
            },
            {
                'key': 'break_minutes',
                'label': '短休息时长',
                'type': 'int',
                'default': 5,
                'min': 1,
                'max': 30,
                'suffix': '分钟',
                'help': '每轮工作后的短休息时间',
            },
            {
                'key': 'long_break_minutes',
                'label': '长休息时长',
                'type': 'int',
                'default': 15,
                'min': 5,
                'max': 60,
                'suffix': '分钟',
                'help': '完成指定轮数后的长休息时间',
            },
            {
                'key': 'rounds_before_long_break',
                'label': '长休息前轮数',
                'type': 'int',
                'default': 4,
                'min': 2,
                'max': 10,
                'suffix': '轮',
                'help': '完成多少轮后进入长休息',
            },
        ]

    def on_config_changed(self, key, value):
        """配置变更时实时更新内部参数"""
        if key == 'work_minutes':
            self._work_minutes = value
        elif key == 'break_minutes':
            self._break_minutes = value
        elif key == 'long_break_minutes':
            self._long_break_minutes = value
        elif key == 'rounds_before_long_break':
            self._rounds_before_long_break = value

    def start_pomodoro(self):
        """开始番茄钟"""
        if self._timer.isActive():
            self.show_notification('🍅 番茄钟', '番茄钟已在运行中')
            return

        self._is_working = True
        self._current_round = 0
        self._remaining = self._work_minutes * 60
        self._timer.start(1000)
        self.show_notification(
            '🍅 番茄钟已启动',
            f'工作时间 {self._work_minutes} 分钟，专注工作吧！'
        )

    def stop_pomodoro(self):
        """停止番茄钟"""
        self._timer.stop()
        self._remaining = 0
        self._current_round = 0
        self.show_notification('🍅 番茄钟已停止', '计时器已重置')

    def _tick(self):
        """每秒递减"""
        self._remaining -= 1

        if self._remaining <= 0:
            self._timer.stop()
            if self._is_working:
                # 工作结束
                self._current_round += 1
                if self._current_round >= self._rounds_before_long_break:
                    # 进入长休息
                    self.show_notification(
                        '🍅 工作轮次完成！',
                        f'已完成 {self._current_round} 轮，长休息 {self._long_break_minutes} 分钟。'
                    )
                    self._is_working = False
                    self._remaining = self._long_break_minutes * 60
                    self._current_round = 0  # 重置轮次
                    self._timer.start(1000)
                else:
                    # 短休息
                    self.show_notification(
                        '🍅 工作时间结束！',
                        f'第 {self._current_round}/{self._rounds_before_long_break} 轮完成，'
                        f'休息 {self._break_minutes} 分钟。'
                    )
                    self._is_working = False
                    self._remaining = self._break_minutes * 60
                    self._timer.start(1000)
            else:
                # 休息结束，开始下一轮工作
                self.show_notification(
                    '🍅 休息结束！',
                    f'精力恢复，开始第 {self._current_round + 1} 轮工作！'
                )
                self._is_working = True
                self._remaining = self._work_minutes * 60
                self._timer.start(1000)

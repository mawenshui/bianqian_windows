import os
import json
from PyQt5.QtCore import QTimer, QDateTime, QObject, pyqtSignal
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QDateTimeEdit, QComboBox, QPushButton, QCheckBox, QFormLayout, QMessageBox, QApplication

class ReminderManager(QObject):
    """
    提醒管理器
    """
    reminder_triggered = pyqtSignal(str, str)  # 便签ID, 提醒消息
    
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.reminders = {}
        self.reminders_file = os.path.join(os.getcwd(), 'reminders.json')
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_reminders)
        self.timer.start(60000)  # 每分钟检查一次
        self.load_reminders()
    
    def add_reminder(self, note_id, datetime, repeat_type='none', message=''):
        """
        添加提醒
        
        Args:
            note_id: 便签ID
            datetime: 提醒时间
            repeat_type: 重复类型 ('none', 'daily', 'weekly', 'monthly')
            message: 提醒消息
        """
        reminder = {
            'note_id': note_id,
            'datetime': datetime.toString(),
            'repeat_type': repeat_type,
            'message': message,
            'enabled': True
        }
        
        reminder_id = f"{note_id}_{datetime.toString('yyyyMMddHHmmss')}"
        self.reminders[reminder_id] = reminder
        self.save_reminders()
        return reminder_id
    
    def remove_reminder(self, reminder_id):
        """
        移除提醒
        
        Args:
            reminder_id: 提醒ID
        """
        if reminder_id in self.reminders:
            del self.reminders[reminder_id]
            self.save_reminders()
    
    def update_reminder(self, reminder_id, datetime=None, repeat_type=None, message=None, enabled=None):
        """
        更新提醒
        
        Args:
            reminder_id: 提醒ID
            datetime: 提醒时间
            repeat_type: 重复类型
            message: 提醒消息
            enabled: 是否启用
        """
        if reminder_id in self.reminders:
            if datetime:
                self.reminders[reminder_id]['datetime'] = datetime.toString()
            if repeat_type:
                self.reminders[reminder_id]['repeat_type'] = repeat_type
            if message is not None:
                self.reminders[reminder_id]['message'] = message
            if enabled is not None:
                self.reminders[reminder_id]['enabled'] = enabled
            self.save_reminders()
    
    def check_reminders(self):
        """
        检查并触发到期的提醒
        """
        current_time = QDateTime.currentDateTime()
        
        for reminder_id, reminder in list(self.reminders.items()):
            if not reminder['enabled']:
                continue
            
            reminder_time = QDateTime.fromString(reminder['datetime'])
            
            if current_time >= reminder_time:
                self.trigger_reminder(reminder)
                
                # 处理重复提醒
                if reminder['repeat_type'] != 'none':
                    self.schedule_next_reminder(reminder_id, reminder)
                else:
                    del self.reminders[reminder_id]
                
                self.save_reminders()
    
    def trigger_reminder(self, reminder):
        """
        触发提醒通知
        
        Args:
            reminder: 提醒信息
        """
        note_id = reminder['note_id']
        message = reminder['message']
        
        if note_id in self.manager.notes:
            note = self.manager.notes[note_id]
            title = note.note_data.get('title', f'便签 {note_id}')
            
            # 显示系统通知
            self.manager.tray_icon.showMessage(
                f"便签提醒: {title}",
                message or "您有一个便签提醒",
                QApplication.style().standardIcon(QApplication.style().SP_MessageBoxInformation),
                5000
            )
            
            # 可选：打开便签窗口
            note.show()
            note.raise_()
            note.activateWindow()
        
        # 发出信号
        self.reminder_triggered.emit(note_id, message)
    
    def schedule_next_reminder(self, reminder_id, reminder):
        """
        安排下一次重复提醒
        
        Args:
            reminder_id: 提醒ID
            reminder: 提醒信息
        """
        reminder_time = QDateTime.fromString(reminder['datetime'])
        
        # 根据重复类型计算下一次提醒时间
        if reminder['repeat_type'] == 'daily':
            next_time = reminder_time.addDays(1)
        elif reminder['repeat_type'] == 'weekly':
            next_time = reminder_time.addDays(7)
        elif reminder['repeat_type'] == 'monthly':
            next_time = reminder_time.addMonths(1)
        else:
            return
        
        # 更新提醒时间
        self.reminders[reminder_id]['datetime'] = next_time.toString()
    
    def get_reminders_for_note(self, note_id):
        """
        获取便签的所有提醒
        
        Args:
            note_id: 便签ID
            
        Returns:
            提醒列表
        """
        return [(rid, rem) for rid, rem in self.reminders.items() if rem['note_id'] == note_id]
    
    def load_reminders(self):
        """
        从文件加载提醒
        """
        if os.path.exists(self.reminders_file):
            try:
                with open(self.reminders_file, 'r', encoding='utf-8') as f:
                    self.reminders = json.load(f)
            except Exception as e:
                print(f"加载提醒失败: {e}")
    
    def save_reminders(self):
        """
        保存提醒到文件
        """
        try:
            with open(self.reminders_file, 'w', encoding='utf-8') as f:
                json.dump(self.reminders, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存提醒失败: {e}")

class ReminderDialog(QDialog):
    """
    提醒设置对话框
    """
    def __init__(self, note_id, reminder_manager, parent=None):
        super().__init__(parent)
        self.note_id = note_id
        self.reminder_manager = reminder_manager
        self.reminders = self.reminder_manager.get_reminders_for_note(note_id)
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle('设置提醒')
        self.setFixedSize(400, 300)
        
        layout = QVBoxLayout()
        
        # 提醒时间
        time_layout = QFormLayout()
        self.time_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.time_edit.setCalendarPopup(True)
        time_layout.addRow('提醒时间:', self.time_edit)
        layout.addLayout(time_layout)
        
        # 重复类型
        repeat_layout = QFormLayout()
        self.repeat_combo = QComboBox()
        self.repeat_combo.addItems(['不重复', '每天', '每周', '每月'])
        self.repeat_combo.setCurrentIndex(0)
        repeat_layout.addRow('重复:', self.repeat_combo)
        layout.addLayout(repeat_layout)
        
        # 提醒消息
        message_layout = QFormLayout()
        self.message_edit = QLabel()
        self.message_edit.setText('提醒消息:')
        self.message_text = QLabel()
        self.message_text.setText('(可选)')
        message_layout.addRow(self.message_edit, self.message_text)
        layout.addLayout(message_layout)
        
        # 已有的提醒
        if self.reminders:
            reminders_group = QVBoxLayout()
            reminders_label = QLabel('已设置的提醒:')
            reminders_group.addWidget(reminders_label)
            
            for reminder_id, reminder in self.reminders:
                reminder_time = QDateTime.fromString(reminder['datetime'])
                repeat_text = {
                    'none': '不重复',
                    'daily': '每天',
                    'weekly': '每周',
                    'monthly': '每月'
                }.get(reminder['repeat_type'], '不重复')
                
                reminder_item = QHBoxLayout()
                reminder_info = QLabel(f"{reminder_time.toString('yyyy-MM-dd HH:mm')} ({repeat_text})")
                delete_btn = QPushButton('删除')
                delete_btn.setFixedSize(60, 25)
                delete_btn.clicked.connect(lambda _, rid=reminder_id: self.delete_reminder(rid))
                
                reminder_item.addWidget(reminder_info)
                reminder_item.addStretch()
                reminder_item.addWidget(delete_btn)
                reminders_group.addLayout(reminder_item)
            
            layout.addLayout(reminders_group)
        
        # 按钮
        button_layout = QHBoxLayout()
        add_btn = QPushButton('添加提醒')
        add_btn.clicked.connect(self.add_reminder)
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(add_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def add_reminder(self):
        """
        添加提醒
        """
        reminder_time = self.time_edit.dateTime()
        repeat_type = ['none', 'daily', 'weekly', 'monthly'][self.repeat_combo.currentIndex()]
        message = ""
        
        # 检查时间是否有效
        if reminder_time < QDateTime.currentDateTime():
            QMessageBox.warning(self, '时间无效', '提醒时间必须晚于当前时间')
            return
        
        # 添加提醒
        self.reminder_manager.add_reminder(self.note_id, reminder_time, repeat_type, message)
        QMessageBox.information(self, '添加成功', '提醒已添加')
        self.accept()
    
    def delete_reminder(self, reminder_id):
        """
        删除提醒
        
        Args:
            reminder_id: 提醒ID
        """
        reply = QMessageBox.question(
            self, '删除提醒',
            '确定要删除这个提醒吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.reminder_manager.remove_reminder(reminder_id)
            QMessageBox.information(self, '删除成功', '提醒已删除')
            self.initUI()  # 刷新界面

# -*- coding: utf-8 -*-
"""
锁定对话框模块

提供密码输入、密码设置和主密码验证的对话框。
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QWidget
)
from PyQt5.QtCore import Qt


def _create_password_field(placeholder: str = '输入密码...'):
    """
    创建带可见/不可见切换按钮的密码输入框。
    
    Returns:
        (QWidget, QLineEdit): 包含密码输入框和切换按钮的组合控件
    """
    container = QWidget()
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    
    pwd_input = QLineEdit()
    pwd_input.setEchoMode(QLineEdit.Password)
    pwd_input.setPlaceholderText(placeholder)
    layout.addWidget(pwd_input)
    
    toggle_btn = QPushButton('👁')
    toggle_btn.setFixedSize(32, 28)
    toggle_btn.setToolTip('显示/隐藏密码')
    toggle_btn.setCheckable(True)
    toggle_btn.setStyleSheet(
        'QPushButton { border: 1px solid #ccc; border-radius: 3px; padding: 2px; }'
        'QPushButton:checked { background-color: #e0e0e0; }'
    )
    
    def _toggle_visibility(checked):
        if checked:
            pwd_input.setEchoMode(QLineEdit.Normal)
            toggle_btn.setText('🔒')
        else:
            pwd_input.setEchoMode(QLineEdit.Password)
            toggle_btn.setText('👁')
    
    toggle_btn.toggled.connect(_toggle_visibility)
    layout.addWidget(toggle_btn)
    
    container.setLayout(layout)
    return container, pwd_input


class PasswordInputDialog(QDialog):
    """解锁时的密码输入对话框"""

    def __init__(self, note_title: str = '', parent=None):
        super().__init__(parent)
        self.setWindowTitle('解锁便签')
        self.setFixedSize(350, 180)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self._password = ''
        self._init_ui(note_title)

    def _init_ui(self, note_title: str):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title_label = QLabel(f'🔒 便签 "{note_title}" 已锁定')
        title_label.setStyleSheet('font-size: 12pt; font-weight: bold;')
        layout.addWidget(title_label)

        hint_label = QLabel('请输入密码以解锁：')
        layout.addWidget(hint_label)

        pwd_widget, self.password_input = _create_password_field('输入密码...')
        self.password_input.returnPressed.connect(self._on_accept)
        layout.addWidget(pwd_widget)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        unlock_btn = QPushButton('🔓 解锁')
        unlock_btn.setStyleSheet(
            'QPushButton { background-color: #007acc; color: white; padding: 6px 16px; border-radius: 4px; }'
            'QPushButton:hover { background-color: #005a9e; }'
        )
        unlock_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(unlock_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _on_accept(self):
        self._password = self.password_input.text()
        if not self._password:
            QMessageBox.warning(self, '提示', '请输入密码')
            return
        self.accept()

    def get_password(self) -> str:
        return self._password


class SetPasswordDialog(QDialog):
    """设置/修改便签密码的对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('设置便签密码')
        self.setFixedSize(350, 220)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self._password = ''
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        title_label = QLabel('🔒 设置便签锁定密码')
        title_label.setStyleSheet('font-size: 12pt; font-weight: bold;')
        layout.addWidget(title_label)

        hint_label = QLabel('设置密码后，便签内容将被加密保护。')
        hint_label.setStyleSheet('color: #666;')
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        pwd_widget, self.password_input = _create_password_field('输入新密码...')
        layout.addWidget(pwd_widget)

        self.confirm_widget, self.confirm_input = _create_password_field('确认密码...')
        self.confirm_input.returnPressed.connect(self._on_accept)
        layout.addWidget(self.confirm_widget)

        # 密码可见时隐藏确认框（可见时已能确认密码正确性）
        self._pwd_toggle_btn = pwd_widget.layout().itemAt(1).widget()
        self._confirm_toggle_btn = self.confirm_widget.layout().itemAt(1).widget()
        self._pwd_toggle_btn.toggled.connect(self._on_pwd_visibility_changed)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        set_btn = QPushButton('确定')
        set_btn.setStyleSheet(
            'QPushButton { background-color: #007acc; color: white; padding: 6px 16px; border-radius: 4px; }'
            'QPushButton:hover { background-color: #005a9e; }'
        )
        set_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(set_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _on_pwd_visibility_changed(self, visible):
        """密码可见时隐藏确认框（已能直接看到密码，无需确认）"""
        self.confirm_widget.setVisible(not visible)

    def _on_accept(self):
        pwd = self.password_input.text()
        is_visible = self.password_input.echoMode() == QLineEdit.Normal

        if not pwd:
            QMessageBox.warning(self, '提示', '请输入密码')
            return
        if len(pwd) < 4:
            QMessageBox.warning(self, '提示', '密码长度至少为 4 个字符')
            return
        # 密码不可见时才需要确认
        if not is_visible:
            confirm = self.confirm_input.text()
            if pwd != confirm:
                QMessageBox.warning(self, '提示', '两次输入的密码不一致')
                return

        self._password = pwd
        self.accept()

    def get_password(self) -> str:
        return self._password


class MasterPasswordDialog(QDialog):
    """启动时的主密码验证对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('应用解锁')
        self.setFixedSize(400, 220)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setModal(True)
        self._password = ''
        self._reset_requested = False
        self._reset_mode = 0  # 0=未请求, 1=仅删便签, 2=删除便签+重置设置
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        title_label = QLabel('🔐 桌面便签 — 需要主密码')
        title_label.setStyleSheet('font-size: 14pt; font-weight: bold;')
        layout.addWidget(title_label)

        hint_label = QLabel('此应用已启用主密码保护，请输入主密码以继续：')
        hint_label.setStyleSheet('color: #666;')
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        pwd_widget, self.password_input = _create_password_field('输入主密码...')
        self.password_input.returnPressed.connect(self._on_accept)
        layout.addWidget(pwd_widget)

        btn_layout = QHBoxLayout()

        reset_btn = QPushButton('⚠ 重置应用')
        reset_btn.setToolTip('忘记密码？重置应用将清除主密码，可选删除便签数据')
        reset_btn.setStyleSheet(
            'QPushButton { color: #e67e22; border: 1px solid #e67e22; padding: 6px 12px; border-radius: 4px; }'
            'QPushButton:hover { background-color: #fdf2e9; }'
        )
        reset_btn.clicked.connect(self._on_reset_clicked)
        btn_layout.addWidget(reset_btn)

        btn_layout.addStretch()

        exit_btn = QPushButton('退出应用')
        exit_btn.setStyleSheet('color: #e74c3c;')
        exit_btn.clicked.connect(self.reject)
        btn_layout.addWidget(exit_btn)

        unlock_btn = QPushButton('🔓 解锁')
        unlock_btn.setStyleSheet(
            'QPushButton { background-color: #27ae60; color: white; padding: 6px 20px; border-radius: 4px; }'
            'QPushButton:hover { background-color: #219a52; }'
        )
        unlock_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(unlock_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _on_reset_clicked(self):
        """显示重置选项对话框"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle('重置应用')
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setText(
            '⚠️ 重置应用将清除主密码保护。\n\n'
            '请选择重置方式：'
        )
        msg_box.setInformativeText(
            '• 仅删除便签：保留所有设置，仅删除全部便签数据\n'
            '• 完全重置：删除所有便签并恢复出厂设置'
        )

        notes_only_btn = msg_box.addButton('仅删除所有便签', QMessageBox.DestructiveRole)
        full_reset_btn = msg_box.addButton('完全重置（便签+设置）', QMessageBox.DestructiveRole)
        cancel_btn = msg_box.addButton('取消', QMessageBox.RejectRole)

        msg_box.setDefaultButton(cancel_btn)
        msg_box.exec_()

        clicked = msg_box.clickedButton()
        if clicked == notes_only_btn:
            # 二次确认
            confirm = QMessageBox.question(
                self, '确认操作',
                '确定要删除所有便签数据吗？\n\n此操作不可撤销！',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                self._reset_requested = True
                self._reset_mode = 1
                self.accept()
        elif clicked == full_reset_btn:
            confirm = QMessageBox.question(
                self, '确认操作',
                '确定要删除所有便签并恢复出厂设置吗？\n\n此操作不可撤销！所有数据将永久丢失。',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                self._reset_requested = True
                self._reset_mode = 2
                self.accept()

    def _on_accept(self):
        self._password = self.password_input.text()
        if not self._password:
            QMessageBox.warning(self, '提示', '请输入主密码')
            return
        self.accept()

    def get_password(self) -> str:
        return self._password

    @property
    def reset_requested(self) -> bool:
        return self._reset_requested

    @property
    def reset_mode(self) -> int:
        return self._reset_mode


class SetMasterPasswordDialog(QDialog):
    """设置主密码的对话框（在设置对话框中使用）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('设置主密码')
        self.setFixedSize(400, 250)
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self._password = ''
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        title_label = QLabel('🔐 设置应用主密码')
        title_label.setStyleSheet('font-size: 12pt; font-weight: bold;')
        layout.addWidget(title_label)

        hint_label = QLabel(
            '启用主密码后，每次启动应用都需要输入密码。\n'
            '⚠️ 请牢记密码，忘记后将无法访问便签数据！'
        )
        hint_label.setStyleSheet('color: #e67e22;')
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        pwd_widget, self.password_input = _create_password_field('输入新主密码...')
        layout.addWidget(pwd_widget)

        self.confirm_widget, self.confirm_input = _create_password_field('确认主密码...')
        self.confirm_input.returnPressed.connect(self._on_accept)
        layout.addWidget(self.confirm_widget)

        # 密码可见时隐藏确认框
        self._pwd_toggle_btn = pwd_widget.layout().itemAt(1).widget()
        self._pwd_toggle_btn.toggled.connect(self._on_pwd_visibility_changed)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        set_btn = QPushButton('确定启用')
        set_btn.setStyleSheet(
            'QPushButton { background-color: #e67e22; color: white; padding: 6px 16px; border-radius: 4px; }'
            'QPushButton:hover { background-color: #d35400; }'
        )
        set_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(set_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _on_pwd_visibility_changed(self, visible):
        """密码可见时隐藏确认框"""
        self.confirm_widget.setVisible(not visible)

    def _on_accept(self):
        pwd = self.password_input.text()
        is_visible = self.password_input.echoMode() == QLineEdit.Normal

        if not pwd:
            QMessageBox.warning(self, '提示', '请输入主密码')
            return
        if len(pwd) < 6:
            QMessageBox.warning(self, '提示', '主密码长度至少为 6 个字符')
            return
        # 密码不可见时才需要确认
        if not is_visible:
            confirm = self.confirm_input.text()
            if pwd != confirm:
                QMessageBox.warning(self, '提示', '两次输入的密码不一致')
                return

        self._password = pwd
        self.accept()

    def get_password(self) -> str:
        return self._password

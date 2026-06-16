# -*- coding: utf-8 -*-
'''
StickyNote Entry Point
'''
import sys
import signal
import ctypes

# ── 全局引用，供信号处理器访问 ──
_app_instance = None


def _sigint_handler(signum, frame):
    """Ctrl+C 信号处理：通知 Qt 事件循环优雅退出"""
    if _app_instance is not None:
        _app_instance.quit()
    else:
        sys.exit(0)


def _check_single_instance():
    """
    单实例检测：通过 Windows 命名互斥体防止重复启动。
    
    Returns:
        True  — 这是第一个实例，正常启动
        False — 已有实例在运行（已弹窗提示），应退出
        (非 Windows 平台始终返回 True)
    """
    if sys.platform != 'win32':
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        mutex_name = 'Local\\StickyNoteApp_SingleInstance_v1'
        mutex = kernel32.CreateMutexW(None, False, mutex_name)
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            # 已有实例在运行，弹窗提示后返回 False
            ctypes.windll.user32.MessageBoxW(
                0,
                '桌面便签已经在运行中（可能已最小化到系统托盘）。\n'
                '请右键点击托盘图标操作，或退出后重新启动。',
                '桌面便签',
                0x00000030  # MB_ICONWARNING | MB_OK
            )
            return False
        # 第一个实例，持有互斥体句柄（通过闭包保持引用）
        _check_single_instance._mutex = mutex
        return True
    except OSError:
        return True  # 检测失败时允许继续运行


def _check_master_password():
    """
    检查主密码是否已启用，若启用则要求用户输入密码验证。
    
    Returns:
        True  — 未启用主密码 或 验证通过 或 重置完成
        False — 验证失败（用户退出或密码错误）
    """
    import os
    import shutil

    from core.config import get_config
    config = get_config()
    if not config.get('security.require_master_password', False):
        return True  # 未启用主密码
    
    master_hash = config.get('security.master_password_hash', '')
    master_salt_str = config.get('security.master_password_salt', '')
    if not master_hash:
        return True  # 无密码哈希，允许进入
    
    # 将 base64 编码的盐值解码为 bytes
    import base64
    master_salt = None
    if master_salt_str:
        try:
            master_salt = base64.b64decode(master_salt_str)
        except Exception:
            master_salt = None
    
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from features.lock_dialog import MasterPasswordDialog
    from features.encryption import NoteEncryption
    
    enc = NoteEncryption()
    max_attempts = 3
    
    for attempt in range(max_attempts):
        dialog = MasterPasswordDialog()
        if dialog.exec_() != MasterPasswordDialog.Accepted:
            return False  # 用户点击"退出应用"
        
        # 检查是否为重置请求
        if dialog.reset_requested:
            return _perform_reset(dialog.reset_mode, config)
        
        password = dialog.get_password()
        # 验证密码
        try:
            if enc.verify_password(password, master_hash, master_salt):
                return True
        except Exception:
            pass
        
        remaining = max_attempts - attempt - 1
        if remaining > 0:
            QMessageBox.warning(
                None, '密码错误',
                f'主密码不正确，还剩 {remaining} 次尝试机会。'
            )
    
    QMessageBox.critical(None, '验证失败', '密码错误次数过多，应用将退出。')
    return False


def _perform_reset(mode: int, config) -> bool:
    """
    执行应用重置。

    Args:
        mode: 1 = 仅删除便签，2 = 删除便签 + 重置设置
        config: ConfigManager 实例

    Returns:
        True — 重置完成，应用继续启动（无主密码）
    """
    import os
    import shutil
    import glob

    from PyQt5.QtWidgets import QMessageBox
    from core import get_user_data_dir

    user_data_dir = get_user_data_dir()
    notes_dir = os.path.join(user_data_dir, 'notes')

    try:
        # 1. 删除所有便签文件
        if os.path.exists(notes_dir):
            for f in os.listdir(notes_dir):
                file_path = os.path.join(notes_dir, f)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except Exception:
                    pass

        # 2. 删除链接索引
        links_index = os.path.join(notes_dir, 'links_index.json')
        if os.path.exists(links_index):
            try:
                os.remove(links_index)
            except Exception:
                pass

        # 3. 删除备份文件
        from core import get_project_root
        backups_dir = os.path.join(get_project_root(), 'backups')
        if os.path.exists(backups_dir):
            try:
                shutil.rmtree(backups_dir)
            except Exception:
                pass

        # 4. 清除主密码设置
        config.set('security.master_password_hash', '')
        config.set('security.master_password_salt', '')
        config.set('security.require_master_password', False)

        # 5. 模式2：额外恢复出厂设置
        if mode == 2:
            config.reset()  # 恢复所有设置为默认值

        QMessageBox.information(
            None, '重置完成',
            '应用已重置。主密码已关闭，便签数据已清除。'
            if mode == 1 else
            '应用已完全重置。所有设置已恢复默认，所有数据已清除。'
        )
    except Exception as e:
        QMessageBox.critical(
            None, '重置失败',
            f'重置过程中发生错误：{e}'
        )
        return False

    return True


def main():
    if not _check_single_instance():
        return  # 已有实例在运行，直接退出
    # 安装 Ctrl+C 信号处理器
    signal.signal(signal.SIGINT, _sigint_handler)
    # 创建 QApplication（主密码对话框需要，后续由 StickyNoteManager 复用）
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    # 主密码验证
    if not _check_master_password():
        return
    # 不复用 app，由 StickyNoteManager.__init__ 通过 QApplication.instance() 检测并复用
    from core.manager import StickyNoteManager
    global _app_instance
    manager = StickyNoteManager()
    _app_instance = manager.app
    manager.run()


if __name__ == '__main__':
    main()

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
    except Exception:
        return True  # 检测失败时允许继续运行


def main():
    if not _check_single_instance():
        return  # 已有实例在运行，直接退出
    # 安装 Ctrl+C 信号处理器
    signal.signal(signal.SIGINT, _sigint_handler)
    from core.manager import StickyNoteManager
    global _app_instance
    manager = StickyNoteManager()
    _app_instance = manager.app
    manager.run()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3

# 测试模块导入
print("Testing module imports...")

try:
    from PyQt5.QtWidgets import (
        QApplication, QWidget, QTextEdit, QVBoxLayout, QHBoxLayout,
        QPushButton, QSlider, QLabel, QMessageBox, QCheckBox,
        QColorDialog, QFrame, QDialog, QLineEdit, QListWidget, QListWidgetItem,
        QInputDialog, QSystemTrayIcon, QMenu, QAction, QTabWidget,
        QFormLayout, QComboBox, QGroupBox, QFontComboBox, QSpinBox
    )
    print("✓ PyQt5.QtWidgets imported successfully")
except Exception as e:
    print(f"✗ Failed to import PyQt5.QtWidgets: {e}")

try:
    from PyQt5.QtCore import Qt, QPoint, QRect, QMimeData, QSize, pyqtSignal
    print("✓ PyQt5.QtCore imported successfully")
except Exception as e:
    print(f"✗ Failed to import PyQt5.QtCore: {e}")

try:
    from PyQt5.QtGui import QFont, QColor, QPalette, QCursor, QTextCursor, QIcon
    print("✓ PyQt5.QtGui imported successfully")
except Exception as e:
    print(f"✗ Failed to import PyQt5.QtGui: {e}")

try:
    from features.search import SearchManager
    print("✓ features.search imported successfully")
except Exception as e:
    print(f"✗ Failed to import features.search: {e}")

try:
    from features.shortcuts import ShortcutManager
    print("✓ features.shortcuts imported successfully")
except Exception as e:
    print(f"✗ Failed to import features.shortcuts: {e}")

try:
    from features.backup import BackupManager
    print("✓ features.backup imported successfully")
except Exception as e:
    print(f"✗ Failed to import features.backup: {e}")

try:
    from features.positioning import get_position_manager
    print("✓ features.positioning imported successfully")
except Exception as e:
    print(f"✗ Failed to import features.positioning: {e}")

try:
    from features.formatter import ContentFormatter
    print("✓ features.formatter imported successfully")
except Exception as e:
    print(f"✗ Failed to import features.formatter: {e}")

try:
    from features.tags import TagManager
    print("✓ features.tags imported successfully")
except Exception as e:
    print(f"✗ Failed to import features.tags: {e}")

try:
    from features.groups import GroupManager
    print("✓ features.groups imported successfully")
except Exception as e:
    print(f"✗ Failed to import features.groups: {e}")

try:
    from core.sticky_note import StickyNote
    print("✓ core.sticky_note imported successfully")
except Exception as e:
    print(f"✗ Failed to import core.sticky_note: {e}")

try:
    from core.sticky_note_manager import StickyNoteManager
    print("✓ core.sticky_note_manager imported successfully")
except Exception as e:
    print(f"✗ Failed to import core.sticky_note_manager: {e}")

print("Import test completed!")

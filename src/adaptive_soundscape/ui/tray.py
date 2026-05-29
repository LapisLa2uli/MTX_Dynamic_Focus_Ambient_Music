"""Optional system tray integration."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


def create_tray(show_action: QAction, quit_action: QAction) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QSystemTrayIcon()
    tray.setIcon(QIcon())
    tray.setToolTip("Adaptive Soundscape")
    menu = QMenu()
    menu.addAction(show_action)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    return tray

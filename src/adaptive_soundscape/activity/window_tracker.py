"""Windows active window tracking via pywin32."""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowInfo:
    title: str
    process_name: str


def get_active_window() -> WindowInfo:
    """Return active window title and process name (metadata only)."""
    if sys.platform != "win32":
        return WindowInfo(title="", process_name="")

    try:
        import win32gui
        import win32process
        import psutil
    except ImportError:
        return WindowInfo(title="", process_name="")

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return WindowInfo(title="", process_name="")

    title = win32gui.GetWindowText(hwnd) or ""
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    process_name = ""
    try:
        process_name = psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        process_name = ""

    return WindowInfo(title=title, process_name=process_name)

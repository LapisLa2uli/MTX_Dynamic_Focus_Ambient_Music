"""Windows active window tracking via pywin32."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowInfo:
    title: str
    process_name: str


# Shell / input hosts that are not useful to classify as work windows.
_SKIP_PROCESSES = frozenset(
    {
        "explorer",
        "textinputhost",
        "applicationframehost",
        "searchapp",
        "searchhost",
        "shellexperiencehost",
        "startmenuexperiencehost",
        "runtimebroker",
        "dwm",
        "lockapp",
        "sihost",
        "ctfmon",
    }
)


def get_active_window() -> WindowInfo:
    """Return active window title and process name (metadata only)."""
    if sys.platform != "win32":
        return WindowInfo(title="", process_name="")

    try:
        import psutil
        import win32gui
        import win32process
    except ImportError:
        return WindowInfo(title="", process_name="")

    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return WindowInfo(title="", process_name="")
    return _info_from_hwnd(hwnd, psutil=psutil, win32gui=win32gui, win32process=win32process)


def list_open_windows(*, skip_pids: frozenset[int] | None = None) -> list[WindowInfo]:
    """Visible top-level windows with a title (excludes tool windows and *skip_pids*)."""
    if sys.platform != "win32":
        return []
    try:
        import psutil
        import win32con
        import win32gui
        import win32process
    except ImportError:
        return []

    skip = set(skip_pids or ())
    skip.add(os.getpid())
    found: list[WindowInfo] = []
    seen: set[tuple[str, str]] = set()

    def _callback(hwnd: int, _extra) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return True
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if ex_style & win32con.WS_EX_TOOLWINDOW:
            return True
        title = (win32gui.GetWindowText(hwnd) or "").strip()
        if not title:
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return True
        if pid in skip:
            return True
        info = _info_from_hwnd(
            hwnd, psutil=psutil, win32gui=win32gui, win32process=win32process
        )
        if not info.process_name and not info.title:
            return True
        base = info.process_name.lower().removesuffix(".exe")
        if base in _SKIP_PROCESSES:
            return True
        key = (info.process_name.lower(), info.title.lower())
        if key in seen:
            return True
        seen.add(key)
        found.append(info)
        return True

    win32gui.EnumWindows(_callback, None)
    return found


def _info_from_hwnd(hwnd: int, *, psutil, win32gui, win32process) -> WindowInfo:
    title = win32gui.GetWindowText(hwnd) or ""
    process_name = ""
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process_name = psutil.Process(pid).name()
    except Exception:
        process_name = ""
    return WindowInfo(title=title, process_name=process_name)

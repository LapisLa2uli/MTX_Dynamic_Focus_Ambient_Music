"""Input cadence tracking — counts only, no keystroke content."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class InputCounts:
    keystrokes: int = 0
    clicks: int = 0
    scrolls: int = 0
    last_input_monotonic: float = field(default_factory=time.monotonic)


class InputTracker:
    """Track input event counts without recording key content."""

    def __init__(self) -> None:
        self._counts = InputCounts()
        self._lock = threading.Lock()
        self._listener = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            from pynput import keyboard, mouse

            def on_key_press(_key) -> None:
                with self._lock:
                    self._counts.keystrokes += 1
                    self._counts.last_input_monotonic = time.monotonic()

            def on_click(_x, _y, _button, pressed) -> None:
                if pressed:
                    with self._lock:
                        self._counts.clicks += 1
                        self._counts.last_input_monotonic = time.monotonic()

            def on_scroll(_x, _y, _dx, _dy) -> None:
                with self._lock:
                    self._counts.scrolls += 1
                    self._counts.last_input_monotonic = time.monotonic()

            self._keyboard_listener = keyboard.Listener(on_press=on_key_press)
            self._mouse_listener = mouse.Listener(
                on_click=on_click, on_scroll=on_scroll
            )
            self._keyboard_listener.start()
            self._mouse_listener.start()
        except Exception:
            self._running = False

    def stop(self) -> None:
        self._running = False
        for attr in ("_keyboard_listener", "_mouse_listener"):
            listener = getattr(self, attr, None)
            if listener is not None:
                listener.stop()

    def snapshot_and_reset(self) -> InputCounts:
        with self._lock:
            snapshot = InputCounts(
                keystrokes=self._counts.keystrokes,
                clicks=self._counts.clicks,
                scrolls=self._counts.scrolls,
                last_input_monotonic=self._counts.last_input_monotonic,
            )
            self._counts = InputCounts(last_input_monotonic=self._counts.last_input_monotonic)
            return snapshot

    @property
    def idle_seconds(self) -> float:
        with self._lock:
            return max(0.0, time.monotonic() - self._counts.last_input_monotonic)

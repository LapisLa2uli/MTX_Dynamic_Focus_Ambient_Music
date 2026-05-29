"""Activity monitor orchestrating window, input, and system metrics."""

from __future__ import annotations

from datetime import datetime, timezone

import psutil

from adaptive_soundscape.activity.input_tracker import InputTracker
from adaptive_soundscape.activity.metrics import compute_metrics
from adaptive_soundscape.activity.window_tracker import WindowInfo, get_active_window
from adaptive_soundscape.core.config import PrivacyConfig
from adaptive_soundscape.core.events import ActivitySnapshot


class ActivityMonitor:
    """Polls activity signals and emits privacy-safe snapshots."""

    def __init__(self, privacy: PrivacyConfig) -> None:
        self._privacy = privacy
        self._input = InputTracker()
        self._last_window = WindowInfo(title="", process_name="")
        self._window_switches = 0

    def start(self) -> None:
        self._input.start()

    def stop(self) -> None:
        self._input.stop()

    def poll(self, interval_seconds: float) -> ActivitySnapshot:
        window = get_active_window()
        if (
            window.process_name != self._last_window.process_name
            or window.title != self._last_window.title
        ):
            if self._last_window.process_name or self._last_window.title:
                self._window_switches += 1
            self._last_window = window

        counts = self._input.snapshot_and_reset()
        idle = self._input.idle_seconds
        cpu = psutil.cpu_percent(interval=None)

        title = window.title if self._privacy.collect_window_titles else ""
        process = window.process_name if self._privacy.collect_process_names else ""

        return ActivitySnapshot(
            timestamp=datetime.now(timezone.utc),
            window_title=title,
            process_name=process,
            keystroke_count=counts.keystrokes,
            click_count=counts.clicks,
            scroll_count=counts.scrolls,
            cpu_percent=cpu,
            idle_seconds=idle,
        )

    def metrics(self, snapshot: ActivitySnapshot, interval_seconds: float):
        return compute_metrics(
            keystrokes=snapshot.keystroke_count,
            clicks=snapshot.click_count,
            scrolls=snapshot.scroll_count,
            idle_seconds=snapshot.idle_seconds,
            cpu_percent=snapshot.cpu_percent,
            window_switches=self._window_switches,
            interval_seconds=interval_seconds,
        )

    def reset_window_switches(self) -> None:
        self._window_switches = 0

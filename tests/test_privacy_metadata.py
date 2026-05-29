"""Privacy tests — metadata only, no keystroke content."""

from datetime import datetime, timezone

from adaptive_soundscape.activity.input_tracker import InputTracker
from adaptive_soundscape.activity.monitor import ActivityMonitor
from adaptive_soundscape.core.config import PrivacyConfig
from adaptive_soundscape.core.events import ActivitySnapshot


def test_activity_snapshot_has_counts_not_content():
    snap = ActivitySnapshot(
        timestamp=datetime.now(timezone.utc),
        window_title="Secret Doc",
        process_name="notepad.exe",
        keystroke_count=42,
        click_count=3,
        scroll_count=1,
        cpu_percent=5.0,
        idle_seconds=2.0,
    )
    assert snap.keystroke_count == 42
    payload = snap.__dict__
    assert "key" not in payload
    assert "text" not in payload
    assert "content" not in payload


def test_input_tracker_exposes_counts_only():
    tracker = InputTracker()
    counts = tracker.snapshot_and_reset()
    assert hasattr(counts, "keystrokes")
    assert not hasattr(counts, "keystroke_log")
    assert not hasattr(counts, "key_buffer")


def test_privacy_config_strips_window_metadata():
    privacy = PrivacyConfig(collect_window_titles=False, collect_process_names=False)
    monitor = ActivityMonitor(privacy)
    snap = monitor.poll(1.0)
    assert snap.window_title == ""
    assert snap.process_name == ""

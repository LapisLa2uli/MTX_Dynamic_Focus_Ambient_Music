"""Tests for rule-based context classification."""

from datetime import datetime, timezone

from adaptive_soundscape.context.classifier import classify_snapshot
from adaptive_soundscape.context.persistence import ContextPersistence
from adaptive_soundscape.core.events import ActivitySnapshot, WorkContext


def _snapshot(title: str, process: str) -> ActivitySnapshot:
    return ActivitySnapshot(
        timestamp=datetime.now(timezone.utc),
        window_title=title,
        process_name=process,
        keystroke_count=0,
        click_count=0,
        scroll_count=0,
        cpu_percent=10.0,
        idle_seconds=0.0,
    )


def test_classifies_programming_context():
    result = classify_snapshot(_snapshot("main.py - Cursor", "cursor.exe"))
    assert result.context == WorkContext.PROGRAMMING
    assert result.confidence > 0.5


def test_classifies_distraction_context():
    result = classify_snapshot(_snapshot("Funny Cats - YouTube", "chrome.exe"))
    assert result.context == WorkContext.DISTRACTION


def test_persistence_requires_dwell():
    persistence = ContextPersistence(dwell_seconds=30.0)
    snap = _snapshot("Slack | general", "slack.exe")
    result = classify_snapshot(snap)
    assert persistence.update(result.context, result.confidence) == WorkContext.UNKNOWN
    persistence.candidate_since -= 31.0
    assert persistence.update(result.context, result.confidence) == WorkContext.TEAM_WORKFLOW

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


def test_classifies_programming_context_from_cursor():
    result = classify_snapshot(_snapshot("main.py - Cursor", "cursor.exe"))
    assert result.context == WorkContext.PROGRAMMING
    assert result.confidence > 0.5


def test_classifies_programming_context_from_pycharm_process():
    result = classify_snapshot(_snapshot("Adaptive Soundscape", "pycharm64.exe"))
    assert result.context == WorkContext.PROGRAMMING
    assert result.confidence >= 0.75


def test_classifies_programming_context_from_pycharm_title_and_file():
    result = classify_snapshot(_snapshot("project – classifier.py", "pycharm64.exe"))
    assert result.context == WorkContext.PROGRAMMING
    assert result.confidence > 0.9


def test_classifies_programming_from_code_file_title_in_terminal():
    result = classify_snapshot(_snapshot("python main.py", "WindowsTerminal.exe"))
    assert result.context == WorkContext.PROGRAMMING


def test_classifies_distraction_context():
    result = classify_snapshot(_snapshot("Funny Cats - YouTube", "chrome.exe"))
    assert result.context == WorkContext.DISTRACTION


def test_github_in_browser_is_not_distraction():
    result = classify_snapshot(
        _snapshot("Pull Request #42 · user/repo", "chrome.exe")
    )
    assert result.context != WorkContext.DISTRACTION


def test_persistence_requires_dwell():
    persistence = ContextPersistence(dwell_seconds=15.0, dwell_seconds_min=8.0)
    snap = _snapshot("Slack | general", "slack.exe")
    result = classify_snapshot(snap)
    assert persistence.update(result.context, result.confidence) == WorkContext.UNKNOWN
    persistence.candidate_since -= 16.0
    assert persistence.update(result.context, result.confidence) == WorkContext.TEAM_WORKFLOW


def test_persistence_fast_path_for_strong_match():
    persistence = ContextPersistence(dwell_seconds=15.0, dwell_seconds_min=8.0)
    snap = _snapshot("project – app.py", "pycharm64.exe")
    result = classify_snapshot(snap)
    assert persistence.update(result.context, result.confidence) == WorkContext.UNKNOWN
    persistence.candidate_since -= 9.0
    assert persistence.update(result.context, result.confidence) == WorkContext.PROGRAMMING


def test_persistence_ignores_brief_unknown_blips():
    persistence = ContextPersistence(dwell_seconds=10.0, dwell_seconds_min=5.0)
    programming = classify_snapshot(_snapshot("app.py", "pycharm64.exe"))

    persistence.update(programming.context, programming.confidence)
    persistence.candidate_since -= 6.0
    assert persistence.update(programming.context, programming.confidence) == WorkContext.PROGRAMMING

    unknown = classify_snapshot(_snapshot("", ""))
    for _ in range(3):
        assert persistence.update(unknown.context, unknown.confidence) == WorkContext.PROGRAMMING

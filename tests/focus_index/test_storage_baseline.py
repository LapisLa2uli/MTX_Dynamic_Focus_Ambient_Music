"""Tests for FLI storage, baseline, and service pattern persistence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from adaptive_soundscape.focus_index.baseline import summarize_baseline
from adaptive_soundscape.focus_index.config import FocusIndexConfig
from adaptive_soundscape.focus_index.models import FocusStatus
from adaptive_soundscape.focus_index.service import FocusIndexService
from adaptive_soundscape.focus_index.storage import FocusIndexStorage
from adaptive_soundscape.focus_index.synthetic import aligned_session


def test_baseline_calibrating_vs_active():
    cfg = FocusIndexConfig(min_baseline_windows=10)
    early = summarize_baseline([50.0, 55.0], cfg)
    assert early.status == FocusStatus.CALIBRATING
    values = [40 + i for i in range(12)]
    ready = summarize_baseline(values, cfg)
    assert ready.status == FocusStatus.OK
    assert ready.median is not None
    assert ready.iqr is not None


def test_storage_roundtrip_and_purge(tmp_path: Path):
    db = tmp_path / "fli.sqlite"
    store = FocusIndexStorage(db)
    events = aligned_session()
    store.insert_events(events)
    start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=20)
    loaded = store.load_events(start=start, end=end)
    assert len(loaded) == len(events)
    store.save_pattern(
        task_profile="programming",
        features={"aligned_active_ratio": 1.0, "cat_code_editor": 1.0},
        scope="dedicated",
    )
    assert len(store.load_patterns("programming")) == 1
    exported = store.export_json()
    assert len(exported["events"]) == len(events)
    store.delete_all()
    assert store.load_events(start=start, end=end) == []
    store.close()


def test_service_max_with_calibration_pattern(tmp_path: Path):
    db = tmp_path / "svc.sqlite"
    cfg = FocusIndexConfig(db_path=db, window_seconds=600)
    svc = FocusIndexService(config=cfg, db_path=db)
    for event in aligned_session():
        svc.storage.insert_event(event)
    features = {
        "aligned_active_ratio": 1.0,
        "switches_per_active_min": 0.1,
        "idle_frac": 0.0,
        "idle_event_rate": 0.0,
        "short_burst_rate": 0.0,
        "probe_score": 0.9,
        "cat_code_editor": 0.9,
        "cat_terminal": 0.1,
    }
    svc.storage.save_pattern(
        task_profile="programming", features=features, scope="dedicated"
    )
    end = datetime(2026, 1, 1, 12, 10, 0, tzinfo=timezone.utc)
    result = svc.score_current_window(
        task_profile="programming", now=end, persist=False
    )
    assert result.focus_index is not None
    assert result.measured_focus is not None
    assert result.pattern_similarity is not None
    assert result.focus_index == max(result.measured_focus, result.pattern_focus or 0)

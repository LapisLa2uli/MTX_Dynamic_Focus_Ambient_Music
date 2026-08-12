"""Unit tests for FLI scoring and gated pattern combine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from adaptive_soundscape.focus_index.config import FocusIndexConfig
from adaptive_soundscape.focus_index.models import (
    AppActivityEvent,
    AppCategory,
    AttentionProbeEvent,
    ComponentScores,
    ContextSwitchEvent,
    FocusSource,
    FocusStatus,
    IdleStateEvent,
)
from adaptive_soundscape.focus_index.patterns import cosine_similarity, max_similarity
from adaptive_soundscape.focus_index.scoring import (
    combine_focus,
    score_window,
    weighted_sum,
)
from adaptive_soundscape.focus_index.synthetic import (
    aligned_session,
    distracting_session,
    idle_heavy_session,
    no_activity,
)


START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
END = START + timedelta(minutes=10)
CFG = FocusIndexConfig()


def test_no_activity_insufficient():
    result = score_window(no_activity(), window_start=START, window_end=END, config=CFG)
    assert result.focus_index is None
    assert result.status == FocusStatus.INSUFFICIENT
    assert result.focus_band.value == "uncertain"


def test_aligned_session_high_measured():
    result = score_window(
        aligned_session(), window_start=START, window_end=END, config=CFG
    )
    assert result.measured_focus is not None
    assert result.measured_focus >= 70
    assert result.components.A is not None and result.components.A > 0.9
    assert result.components.P is not None


def test_distracting_switches_lower_score():
    good = score_window(aligned_session(), window_start=START, window_end=END, config=CFG)
    bad = score_window(
        distracting_session(), window_start=START, window_end=END, config=CFG
    )
    assert bad.measured_focus is not None
    assert good.measured_focus is not None
    assert bad.measured_focus < good.measured_focus
    assert bad.components.A is not None and bad.components.A < 0.7


def test_aligned_tool_switches_penalized_lightly():
    events = [
        AppActivityEvent(
            timestamp=START,
            app_category=AppCategory.CODE_EDITOR,
            duration_s=120,
            aligned=True,
            task_profile="programming",
        ),
        ContextSwitchEvent(
            timestamp=START + timedelta(seconds=120),
            from_category=AppCategory.CODE_EDITOR,
            to_category=AppCategory.TERMINAL,
            from_aligned=True,
            to_aligned=True,
            task_profile="programming",
        ),
        AppActivityEvent(
            timestamp=START + timedelta(seconds=121),
            app_category=AppCategory.TERMINAL,
            duration_s=120,
            aligned=True,
            task_profile="programming",
        ),
    ]
    result = score_window(events, window_start=START, window_end=END, config=CFG)
    assert result.components.S is not None
    assert result.components.S > 0.7


def test_long_idle_uncertain():
    result = score_window(
        idle_heavy_session(), window_start=START, window_end=END, config=CFG
    )
    assert result.status == FocusStatus.UNCERTAIN
    assert result.focus_band.value == "uncertain"


def test_missing_probe_renormalizes():
    events = [
        AppActivityEvent(
            timestamp=START,
            app_category=AppCategory.CODE_EDITOR,
            duration_s=300,
            aligned=True,
        )
    ]
    result = score_window(events, window_start=START, window_end=END, config=CFG)
    assert result.components.P is None
    assert result.measured_focus is not None
    assert "probe_missing_or_expired" in result.uncertainties


def test_expired_probe_ignored():
    events = [
        AppActivityEvent(
            timestamp=START,
            app_category=AppCategory.CODE_EDITOR,
            duration_s=300,
            aligned=True,
        ),
        AttentionProbeEvent(
            timestamp=START - timedelta(hours=2),
            accuracy=1.0,
            omission_rate=0.0,
            commission_rate=0.0,
            rt_mean_ms=300,
            rt_std_ms=20,
        ),
    ]
    result = score_window(events, window_start=START, window_end=END, config=CFG)
    assert result.components.P is None


def test_weight_renormalization():
    w = weighted_sum(ComponentScores(A=1.0, S=1.0, I=None, P=None), CFG)
    assert w == pytest.approx(1.0)


def test_combine_max_measured():
    focus, pattern, source = combine_focus(70.0, 0.5)
    assert focus == 70.0
    assert pattern == 50.0
    assert source == FocusSource.MEASURED


def test_combine_pattern_assists_when_measured_ok():
    # measured 55 (>= gate), pattern 0.85 → assist capped at measured+12 = 67
    focus, pattern, source = combine_focus(55.0, 0.85)
    assert focus == pytest.approx(67.0)
    assert pattern == pytest.approx(85.0)
    assert source == FocusSource.PATTERN_SIMILARITY


def test_combine_low_measured_ignores_pattern_floor():
    # Previously max() would keep focus at 85; gated rule trusts measured.
    focus, pattern, source = combine_focus(40.0, 0.85)
    assert focus == pytest.approx(40.0)
    assert pattern == pytest.approx(85.0)
    assert source == FocusSource.MEASURED


def test_combine_tie_and_partial():
    focus, _, source = combine_focus(50.0, 0.5)
    assert source == FocusSource.TIE
    focus, _, source = combine_focus(60.0, None)
    assert focus == 60.0 and source == FocusSource.MEASURED
    focus, _, source = combine_focus(None, 0.7)
    assert focus == pytest.approx(70.0) and source == FocusSource.PATTERN_SIMILARITY
    focus, _, source = combine_focus(None, None)
    assert focus is None and source is None


def test_pattern_similarity_gated_on_distraction():
    a = {"aligned_active_ratio": 1.0, "cat_code_editor": 1.0}
    b = {"aligned_active_ratio": 0.95, "cat_code_editor": 0.9}
    sim = cosine_similarity(a, b)
    assert sim > 0.9
    assert max_similarity(a, [{"features": b}]) == pytest.approx(sim)

    result = score_window(
        distracting_session(),
        window_start=START,
        window_end=END,
        config=CFG,
        pattern_similarity=0.95,
    )
    assert result.pattern_focus == pytest.approx(95.0)
    assert result.measured_focus is not None
    # Distraction measured stays below the gate → pattern cannot floor the score.
    assert result.focus_index == pytest.approx(result.measured_focus)
    assert result.focus_source == FocusSource.MEASURED


def test_uncalibrated_asi_only_ignores_probe_and_pattern():
    """Without calibration, measured uses A/S/I only (3-parameter default)."""
    events = distracting_session()
    # Stale-looking probe that would otherwise pull the score.
    events.append(
        AttentionProbeEvent(
            timestamp=END,
            accuracy=1.0,
            omission_rate=0.0,
            commission_rate=0.0,
            rt_mean_ms=280,
            rt_std_ms=15,
        )
    )
    full = score_window(
        events,
        window_start=START,
        window_end=END,
        config=CFG,
        pattern_similarity=0.95,
        measured_keys=("A", "S", "I", "P"),
    )
    asi = score_window(
        events,
        window_start=START,
        window_end=END,
        config=CFG,
        pattern_similarity=None,
        measured_keys=("A", "S", "I"),
    )
    assert "uncalibrated_asi_only" in asi.uncertainties
    assert asi.extras.get("measured_keys") == ["A", "S", "I"]
    assert asi.pattern_focus is None
    assert asi.measured_focus is not None
    assert full.measured_focus is not None
    # Perfect probe should raise full measured above A/S/I-only.
    assert full.measured_focus > asi.measured_focus
    # Distracting ASI score must stay clearly below a high pattern floor.
    assert asi.focus_index == pytest.approx(asi.measured_focus)
    assert asi.focus_index < 70


def test_malformed_idle_still_scores():
    events = [
        IdleStateEvent(timestamp=START, duration_s=10, is_idle=True),
        AppActivityEvent(
            timestamp=START + timedelta(seconds=10),
            app_category=AppCategory.CODE_EDITOR,
            duration_s=200,
            aligned=True,
        ),
    ]
    result = score_window(events, window_start=START, window_end=END, config=CFG)
    assert result.measured_focus is not None

"""Tests for cognitive focus estimation."""

from adaptive_soundscape.cognitive.estimator import FocusEstimator
from adaptive_soundscape.cognitive.signals import FocusSignals
from adaptive_soundscape.core.events import FocusState, WorkContext


def test_high_focus_programming():
    estimator = FocusEstimator(sensitivity=1.0, smoothing=0.0)
    signals = FocusSignals(
        input_rate=0.7,
        switch_rate=0.1,
        idle_ratio=0.05,
        cpu_load=0.2,
        context=WorkContext.PROGRAMMING,
        context_confidence=0.9,
    )
    estimate = estimator.estimate(signals)
    assert estimate.focus_score >= 0.65
    assert estimate.state in (FocusState.DEEP_FOCUS, FocusState.FLOW, FocusState.CALM_PRODUCTIVITY)


def test_distraction_lowers_score():
    estimator = FocusEstimator(sensitivity=1.0, smoothing=0.0)
    signals = FocusSignals(
        input_rate=0.2,
        switch_rate=0.8,
        idle_ratio=0.1,
        cpu_load=0.3,
        context=WorkContext.DISTRACTION,
        context_confidence=0.9,
    )
    estimate = estimator.estimate(signals)
    assert estimate.focus_score < 0.5
    assert estimate.state == FocusState.MILD_DISTRACTION


def test_overstimulation_detection():
    estimator = FocusEstimator(sensitivity=1.0, smoothing=0.0)
    signals = FocusSignals(
        input_rate=0.9,
        switch_rate=0.8,
        idle_ratio=0.0,
        cpu_load=0.5,
        context=WorkContext.TEAM_WORKFLOW,
        context_confidence=0.8,
    )
    estimate = estimator.estimate(signals)
    assert estimate.state == FocusState.OVERSTIMULATION

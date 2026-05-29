"""Tests for transition controller cooldown and hysteresis."""

from adaptive_soundscape.core.events import FocusState, WorkContext
from adaptive_soundscape.transition.controller import TransitionController


def test_profile_change_triggers_transition():
    ctrl = TransitionController(cooldown_seconds=0.0)
    d1 = ctrl.decide(WorkContext.PROGRAMMING, FocusState.DEEP_FOCUS, 0.85)
    assert d1.should_transition
    d2 = ctrl.decide(WorkContext.PROGRAMMING, FocusState.DEEP_FOCUS, 0.86)
    assert not d2.should_transition


def test_cooldown_blocks_minor_state_change():
    ctrl = TransitionController(cooldown_seconds=60.0, hysteresis_threshold=0.08)
    ctrl.decide(WorkContext.PROGRAMMING, FocusState.DEEP_FOCUS, 0.85)
    decision = ctrl.decide(WorkContext.PROGRAMMING, FocusState.CALM_PRODUCTIVITY, 0.84)
    assert not decision.should_transition


def test_distraction_uses_faster_crossfade():
    ctrl = TransitionController(
        deep_focus_crossfade_seconds=12.0,
        distraction_recovery_seconds=4.5,
        cooldown_seconds=0.0,
    )
    decision = ctrl.decide(WorkContext.DISTRACTION, FocusState.MILD_DISTRACTION, 0.3)
    assert decision.should_transition
    assert decision.crossfade_seconds == 4.5


def test_force_profile_bypasses_cooldown():
    ctrl = TransitionController(cooldown_seconds=60.0)
    ctrl.decide(WorkContext.PROGRAMMING, FocusState.DEEP_FOCUS, 0.9)
    forced = ctrl.force_profile(WorkContext.DISTRACTION, FocusState.MILD_DISTRACTION)
    assert forced.should_transition
    assert forced.profile_id == "distraction"

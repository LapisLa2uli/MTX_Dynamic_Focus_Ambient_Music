"""Tests for auto-distraction hysteresis helpers."""

from __future__ import annotations

from adaptive_soundscape.app import AdaptiveSoundscapeApp
from adaptive_soundscape.core.config import Settings
from adaptive_soundscape.core.events import WorkContext


def test_auto_distraction_enter_and_exit(qtbot=None):
    # Construct without showing UI heavily — Settings load is enough.
    # Avoid full Qt if possible: only need the state machine method.
    settings = Settings()
    settings.cognitive.auto_distraction_enabled = True
    settings.cognitive.auto_distraction_enter = 0.38
    settings.cognitive.auto_distraction_exit = 0.50
    settings.cognitive.auto_distraction_dwell_seconds = 0.0  # instant for unit test

    # Lightweight stub object with the method bound from the class
    class _Stub:
        pass

    stub = _Stub()
    stub.settings = settings
    stub._manual_override = False
    stub.calibration = type("C", (), {"force_aligned": False})()
    stub.pomodoro = type("P", (), {"in_session_calibration": False})()
    stub._auto_distract_active = False
    stub._auto_distract_since = 0.0
    stub._update_auto_distraction = AdaptiveSoundscapeApp._update_auto_distraction.__get__(
        stub, AdaptiveSoundscapeApp
    )

    # Low focus → enter distraction immediately (dwell 0)
    out = stub._update_auto_distraction(WorkContext.PROGRAMMING, 0.20)
    assert stub._auto_distract_active is True
    assert out == WorkContext.DISTRACTION

    # Still low → stay
    out = stub._update_auto_distraction(WorkContext.PROGRAMMING, 0.30)
    assert out == WorkContext.DISTRACTION

    # Recover above exit → leave
    out = stub._update_auto_distraction(WorkContext.PROGRAMMING, 0.70)
    assert stub._auto_distract_active is False
    assert out == WorkContext.PROGRAMMING

"""Pomodoro work/break cycling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from adaptive_soundscape.session.pomodoro import PomodoroController, PomodoroPhase


def _expire(pomo: PomodoroController):
    pomo.state.phase_ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    return pomo.tick()


def test_work_expires_into_break():
    pomo = PomodoroController(
        work_minutes=1, break_minutes=1, session_calibration_minutes=0
    )
    pomo.start_work("programming")
    assert pomo.state.phase == PomodoroPhase.WORK
    state = _expire(pomo)
    assert state.phase == PomodoroPhase.BREAK
    assert state.is_active


def test_break_expires_into_next_work_not_idle():
    pomo = PomodoroController(
        work_minutes=1, break_minutes=1, session_calibration_minutes=0
    )
    pomo.start_work("programming")
    _expire(pomo)
    state = _expire(pomo)
    assert state.phase == PomodoroPhase.WORK
    assert state.task_profile == "programming"
    assert state.is_active
    _expire(pomo)
    state = _expire(pomo)
    assert state.phase == PomodoroPhase.WORK
    assert state.is_active


def test_later_cycles_skip_session_calibration():
    pomo = PomodoroController(
        work_minutes=1, break_minutes=1, session_calibration_minutes=5
    )
    pomo.start_work("reading")
    assert pomo.state.phase == PomodoroPhase.SESSION_CALIBRATION
    assert _expire(pomo).phase == PomodoroPhase.BREAK
    nxt = _expire(pomo)
    assert nxt.phase == PomodoroPhase.WORK
    assert nxt.notice == ""


def test_cancel_stops_the_cycle():
    pomo = PomodoroController(
        work_minutes=1, break_minutes=1, session_calibration_minutes=0
    )
    pomo.start_work("programming")
    _expire(pomo)
    assert pomo.in_break
    pomo.cancel()
    assert pomo.state.phase == PomodoroPhase.IDLE
    assert not pomo.state.is_active
    pomo.start_work("programming")
    assert pomo.state.phase == PomodoroPhase.WORK


def test_cancel_restores_first_session_calibration():
    pomo = PomodoroController(
        work_minutes=1, break_minutes=1, session_calibration_minutes=5
    )
    pomo.start_work("programming")
    assert pomo.state.phase == PomodoroPhase.SESSION_CALIBRATION
    pomo.cancel()
    pomo.start_work("programming")
    assert pomo.state.phase == PomodoroPhase.SESSION_CALIBRATION

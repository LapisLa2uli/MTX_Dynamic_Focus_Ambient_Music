"""Pomodoro work/break state machine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class PomodoroPhase(str, Enum):
    IDLE = "idle"
    WORK = "work"
    BREAK = "break"
    SESSION_CALIBRATION = "session_calibration"


@dataclass
class PomodoroState:
    phase: PomodoroPhase = PomodoroPhase.IDLE
    task_profile: str = "default"
    work_minutes: float = 25.0
    break_minutes: float = 5.0
    session_calibration_minutes: float = 5.0
    phase_started_at: datetime | None = None
    phase_ends_at: datetime | None = None
    notice: str = ""

    @property
    def remaining_seconds(self) -> float:
        if self.phase_ends_at is None:
            return 0.0
        now = datetime.now(timezone.utc)
        return max(0.0, (self.phase_ends_at - now).total_seconds())

    @property
    def remaining_fraction(self) -> float:
        """1 at phase start, 0 when the phase ends. Idle returns 0."""
        if self.phase_ends_at is None or self.phase_started_at is None:
            return 0.0
        total = (self.phase_ends_at - self.phase_started_at).total_seconds()
        if total <= 1e-3:
            return 0.0
        return max(0.0, min(1.0, self.remaining_seconds / total))

    @property
    def is_active(self) -> bool:
        return self.phase != PomodoroPhase.IDLE


class PomodoroController:
    """Work/break timer that cycles until cancelled.

    The first work phase of a run may include session calibration; later
    cycles skip it and resume work directly after each break.
    """

    def __init__(
        self,
        *,
        work_minutes: float = 25.0,
        break_minutes: float = 5.0,
        session_calibration_minutes: float = 5.0,
        break_muffling: float = 0.85,
    ) -> None:
        self.work_minutes = work_minutes
        self.break_minutes = break_minutes
        self.session_calibration_minutes = session_calibration_minutes
        self.break_muffling = max(0.0, min(1.0, break_muffling))
        self._calibrate_next_work = True
        self.state = PomodoroState(
            work_minutes=work_minutes,
            break_minutes=break_minutes,
            session_calibration_minutes=session_calibration_minutes,
        )

    def start_work(self, task_profile: str) -> PomodoroState:
        now = datetime.now(timezone.utc)
        calib = (
            min(self.session_calibration_minutes, self.work_minutes)
            if self._calibrate_next_work
            else 0.0
        )
        self.state = PomodoroState(
            phase=PomodoroPhase.SESSION_CALIBRATION
            if calib > 0
            else PomodoroPhase.WORK,
            task_profile=task_profile,
            work_minutes=self.work_minutes,
            break_minutes=self.break_minutes,
            session_calibration_minutes=self.session_calibration_minutes,
            phase_started_at=now,
            phase_ends_at=now + timedelta(minutes=self.work_minutes),
            notice="Calibrating focus for this session (5 min)…"
            if calib > 0
            else "",
        )
        self._calib_ends = now + timedelta(minutes=calib) if calib > 0 else now
        if calib > 0:
            self._calibrate_next_work = False
        return self.state

    def start_break(self) -> PomodoroState:
        now = datetime.now(timezone.utc)
        self.state = PomodoroState(
            phase=PomodoroPhase.BREAK,
            task_profile=self.state.task_profile,
            work_minutes=self.work_minutes,
            break_minutes=self.break_minutes,
            session_calibration_minutes=self.session_calibration_minutes,
            phase_started_at=now,
            phase_ends_at=now + timedelta(minutes=self.break_minutes),
            notice="Break — neutral album, heavy muffling",
        )
        return self.state

    def cancel(self) -> PomodoroState:
        self._calibrate_next_work = True
        self.state = PomodoroState(
            work_minutes=self.work_minutes,
            break_minutes=self.break_minutes,
            session_calibration_minutes=self.session_calibration_minutes,
        )
        return self.state

    def tick(self, now: datetime | None = None) -> PomodoroState:
        if self.state.phase == PomodoroPhase.IDLE:
            return self.state
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if (
            self.state.phase == PomodoroPhase.SESSION_CALIBRATION
            and hasattr(self, "_calib_ends")
            and now >= self._calib_ends
        ):
            self.state.phase = PomodoroPhase.WORK
            self.state.notice = ""

        if self.state.phase_ends_at and now >= self.state.phase_ends_at:
            if self.state.phase in (
                PomodoroPhase.WORK,
                PomodoroPhase.SESSION_CALIBRATION,
            ):
                return self.start_break()
            if self.state.phase == PomodoroPhase.BREAK:
                return self.start_work(self.state.task_profile)
            return self.cancel()
        return self.state

    @property
    def in_session_calibration(self) -> bool:
        return self.state.phase == PomodoroPhase.SESSION_CALIBRATION

    @property
    def in_break(self) -> bool:
        return self.state.phase == PomodoroPhase.BREAK

    def muffling_override(self) -> float | None:
        if self.in_break:
            return self.break_muffling
        return None

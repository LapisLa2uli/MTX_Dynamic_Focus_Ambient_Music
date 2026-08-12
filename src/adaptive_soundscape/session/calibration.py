"""Dedicated and session calibration controllers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class CalibrationKind(str, Enum):
    IDLE = "idle"
    SESSION = "session"
    DEDICATED = "dedicated"


@dataclass
class CalibrationState:
    kind: CalibrationKind = CalibrationKind.IDLE
    task_profile: str = "default"
    duration_minutes: float = 5.0
    started_at: datetime | None = None
    ends_at: datetime | None = None
    notice: str = ""

    @property
    def active(self) -> bool:
        return self.kind != CalibrationKind.IDLE

    @property
    def remaining_seconds(self) -> float:
        if self.ends_at is None:
            return 0.0
        now = datetime.now(timezone.utc)
        return max(0.0, (self.ends_at - now).total_seconds())

    @property
    def progress(self) -> float:
        if self.started_at is None or self.ends_at is None:
            return 0.0
        total = (self.ends_at - self.started_at).total_seconds()
        if total <= 0:
            return 1.0
        done = total - self.remaining_seconds
        return max(0.0, min(1.0, done / total))


class CalibrationController:
    """Tracks dedicated 5–10 min calibration and session calibration windows."""

    def __init__(self) -> None:
        self.state = CalibrationState()
        self._completed = False

    def start_dedicated(
        self, task_profile: str, *, minutes: float = 8.0
    ) -> CalibrationState:
        minutes = max(5.0, min(10.0, float(minutes)))
        now = datetime.now(timezone.utc)
        self._completed = False
        self.state = CalibrationState(
            kind=CalibrationKind.DEDICATED,
            task_profile=task_profile,
            duration_minutes=minutes,
            started_at=now,
            ends_at=now + timedelta(minutes=minutes),
            notice=f"Calibrating focus ({int(minutes)} min) — keep working on your task…",
        )
        return self.state

    def start_session(
        self, task_profile: str, *, minutes: float = 5.0
    ) -> CalibrationState:
        now = datetime.now(timezone.utc)
        self._completed = False
        self.state = CalibrationState(
            kind=CalibrationKind.SESSION,
            task_profile=task_profile,
            duration_minutes=minutes,
            started_at=now,
            ends_at=now + timedelta(minutes=minutes),
            notice="Calibrating focus for this session (5 min)…",
        )
        return self.state

    def cancel(self) -> CalibrationState:
        self.state = CalibrationState()
        self._completed = False
        return self.state

    def tick(self, now: datetime | None = None) -> tuple[CalibrationState, bool]:
        """Return (state, just_completed)."""
        if not self.state.active:
            return self.state, False
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if self.state.ends_at and now >= self.state.ends_at:
            kind = self.state.kind
            profile = self.state.task_profile
            minutes = self.state.duration_minutes
            self._last_completed_kind = kind
            self.state = CalibrationState(
                kind=CalibrationKind.IDLE,
                task_profile=profile,
                duration_minutes=minutes,
                notice=f"Calibration complete ({kind.value}).",
            )
            self._completed = True
            return self.state, True
        return self.state, False

    @property
    def last_completed_kind(self) -> CalibrationKind | None:
        return getattr(self, "_last_completed_kind", None)

    @property
    def force_aligned(self) -> bool:
        return self.state.active

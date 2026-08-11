"""Context persistence with dwell-time hysteresis."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from adaptive_soundscape.core.events import WorkContext


@dataclass
class ContextPersistence:
    """Hold context stable until candidate exceeds dwell threshold."""

    dwell_seconds: float = 5.0
    dwell_seconds_min: float = 3.0
    dwell_seconds_max: float = 8.0
    unknown_grace_polls: int = 4
    current: WorkContext = WorkContext.UNKNOWN
    candidate: WorkContext = WorkContext.UNKNOWN
    candidate_since: float = field(default_factory=time.monotonic)
    last_change: float = field(default_factory=time.monotonic)
    _unknown_streak: int = 0

    def _effective_dwell(self, confidence: float) -> float:
        if confidence >= 0.75:
            return self.dwell_seconds_min
        if confidence >= 0.5:
            return self.dwell_seconds
        return self.dwell_seconds_max

    def update(self, proposed: WorkContext, confidence: float, min_confidence: float = 0.25) -> WorkContext:
        now = time.monotonic()
        if confidence < min_confidence:
            proposed = WorkContext.UNKNOWN

        if proposed == WorkContext.UNKNOWN and self.current != WorkContext.UNKNOWN:
            self._unknown_streak += 1
            if self._unknown_streak < self.unknown_grace_polls:
                return self.current
        else:
            self._unknown_streak = 0

        if proposed == self.current:
            self.candidate = proposed
            self.candidate_since = now
            return self.current

        if proposed != self.candidate:
            self.candidate = proposed
            self.candidate_since = now
            return self.current

        dwell = self._effective_dwell(confidence)
        if now - self.candidate_since >= dwell:
            self.current = proposed
            self.last_change = now
            self.candidate_since = now
            self._unknown_streak = 0
        return self.current

    def force(self, context: WorkContext) -> WorkContext:
        self.current = context
        self.candidate = context
        self.candidate_since = time.monotonic()
        self.last_change = time.monotonic()
        self._unknown_streak = 0
        return self.current

    @property
    def seconds_since_change(self) -> float:
        return time.monotonic() - self.last_change

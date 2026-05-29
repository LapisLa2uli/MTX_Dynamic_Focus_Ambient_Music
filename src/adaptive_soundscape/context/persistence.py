"""Context persistence with dwell-time hysteresis."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from adaptive_soundscape.core.events import WorkContext


@dataclass
class ContextPersistence:
    """Hold context stable until candidate exceeds dwell threshold."""

    dwell_seconds: float = 45.0
    current: WorkContext = WorkContext.UNKNOWN
    candidate: WorkContext = WorkContext.UNKNOWN
    candidate_since: float = field(default_factory=time.monotonic)
    last_change: float = field(default_factory=time.monotonic)

    def update(self, proposed: WorkContext, confidence: float, min_confidence: float = 0.25) -> WorkContext:
        now = time.monotonic()
        if confidence < min_confidence:
            proposed = WorkContext.UNKNOWN

        if proposed == self.current:
            self.candidate = proposed
            self.candidate_since = now
            return self.current

        if proposed != self.candidate:
            self.candidate = proposed
            self.candidate_since = now
            return self.current

        if now - self.candidate_since >= self.dwell_seconds:
            self.current = proposed
            self.last_change = now
            self.candidate_since = now
        return self.current

    def force(self, context: WorkContext) -> WorkContext:
        self.current = context
        self.candidate = context
        self.candidate_since = time.monotonic()
        self.last_change = time.monotonic()
        return self.current

    @property
    def seconds_since_change(self) -> float:
        return time.monotonic() - self.last_change

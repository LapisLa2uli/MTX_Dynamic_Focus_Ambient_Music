"""Go/no-go attention probe contract and result helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean, pstdev

from adaptive_soundscape.focus_index.models import AttentionProbeEvent


@dataclass
class ProbeTrial:
    is_go: bool
    responded: bool
    reaction_ms: float | None = None


@dataclass
class ProbeSessionResult:
    trials: list[ProbeTrial] = field(default_factory=list)
    self_rating: int | None = None
    task_profile: str = "default"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_event(self) -> AttentionProbeEvent:
        go = [t for t in self.trials if t.is_go]
        nogo = [t for t in self.trials if not t.is_go]
        hits = [t for t in go if t.responded]
        misses = [t for t in go if not t.responded]
        false_alarms = [t for t in nogo if t.responded]
        total = max(len(self.trials), 1)
        correct = len(hits) + sum(1 for t in nogo if not t.responded)
        rts = [float(t.reaction_ms) for t in hits if t.reaction_ms is not None]
        rt_mean = float(mean(rts)) if rts else 0.0
        rt_std = float(pstdev(rts)) if len(rts) > 1 else 0.0
        return AttentionProbeEvent(
            timestamp=self.timestamp,
            accuracy=correct / total,
            omission_rate=(len(misses) / max(len(go), 1)),
            commission_rate=(len(false_alarms) / max(len(nogo), 1)),
            rt_mean_ms=rt_mean,
            rt_std_ms=rt_std,
            self_rating=self.self_rating,
            task_profile=self.task_profile,
        )

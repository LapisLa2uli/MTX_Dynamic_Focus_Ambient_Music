"""Signal weights for focus estimation."""

from __future__ import annotations

from dataclasses import dataclass

from adaptive_soundscape.core.events import WorkContext


@dataclass(frozen=True)
class FocusSignals:
    input_rate: float
    switch_rate: float
    idle_ratio: float
    cpu_load: float
    context: WorkContext
    context_confidence: float


CONTEXT_FOCUS_BIAS: dict[WorkContext, float] = {
    WorkContext.PROGRAMMING: 0.15,
    WorkContext.SCIENTIFIC: 0.12,
    WorkContext.READING_WRITING: 0.08,
    WorkContext.CREATIVE_DESIGN: 0.05,
    WorkContext.TEAM_WORKFLOW: -0.05,
    WorkContext.DISTRACTION: -0.35,
    WorkContext.UNKNOWN: 0.0,
}

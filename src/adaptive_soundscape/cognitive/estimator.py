"""Probabilistic cognitive state and focus score estimation."""

from __future__ import annotations

from dataclasses import dataclass

from adaptive_soundscape.cognitive.signals import CONTEXT_FOCUS_BIAS, FocusSignals
from adaptive_soundscape.core.events import FocusState, WorkContext


@dataclass
class FocusEstimate:
    focus_score: float
    state: FocusState
    raw_score: float


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class FocusEstimator:
    """Estimate focus_score (0–1) and discrete cognitive state."""

    def __init__(self, sensitivity: float = 1.0, smoothing: float = 0.85) -> None:
        self.sensitivity = max(0.1, sensitivity)
        self.smoothing = _clamp(smoothing, 0.0, 0.99)
        self._ema_score = 0.5

    def estimate(self, signals: FocusSignals) -> FocusEstimate:
        base = 0.55
        base += signals.input_rate * 0.25 * self.sensitivity
        base -= signals.switch_rate * 0.30 * self.sensitivity
        base -= signals.idle_ratio * 0.20
        base -= signals.cpu_load * 0.05
        base += CONTEXT_FOCUS_BIAS.get(signals.context, 0.0) * signals.context_confidence

        raw = _clamp(base)
        self._ema_score = self.smoothing * self._ema_score + (1.0 - self.smoothing) * raw
        score = _clamp(self._ema_score)
        state = self._classify_state(score, signals)
        return FocusEstimate(focus_score=score, state=state, raw_score=raw)

    def _classify_state(self, score: float, signals: FocusSignals) -> FocusState:
        if signals.context == WorkContext.DISTRACTION and score < 0.45:
            return FocusState.MILD_DISTRACTION
        if signals.switch_rate > 0.65 and signals.input_rate > 0.7:
            return FocusState.OVERSTIMULATION
        if signals.idle_ratio > 0.7 and score < 0.4:
            return FocusState.FATIGUE
        if score >= 0.82 and signals.switch_rate < 0.2:
            return FocusState.FLOW if signals.input_rate > 0.5 else FocusState.DEEP_FOCUS
        if score >= 0.65:
            return FocusState.DEEP_FOCUS
        if score >= 0.45:
            return FocusState.CALM_PRODUCTIVITY
        return FocusState.MILD_DISTRACTION

    def reset(self) -> None:
        self._ema_score = 0.5

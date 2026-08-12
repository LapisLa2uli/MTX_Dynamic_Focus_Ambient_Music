"""Component scores, weighted sum, and final max(measured, pattern) combine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from adaptive_soundscape.focus_index.config import FocusIndexConfig
from adaptive_soundscape.focus_index.models import (
    AppActivityEvent,
    AttentionProbeEvent,
    ComponentScores,
    ContextSwitchEvent,
    FocusBand,
    FocusEvent,
    FocusIndexResult,
    FocusSource,
    FocusStatus,
    IdleStateEvent,
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass
class WindowStats:
    window_s: float
    aligned_active_s: float = 0.0
    total_active_s: float = 0.0
    weighted_switches: float = 0.0
    n_idle: int = 0
    total_idle_s: float = 0.0
    n_short: int = 0
    category_seconds: dict[str, float] | None = None
    latest_probe: AttentionProbeEvent | None = None

    def __post_init__(self) -> None:
        if self.category_seconds is None:
            self.category_seconds = {}


def accumulate_stats(
    events: Iterable[FocusEvent],
    *,
    window_start: datetime,
    window_end: datetime,
    config: FocusIndexConfig,
) -> WindowStats:
    window_s = max((window_end - window_start).total_seconds(), 1e-6)
    stats = WindowStats(window_s=window_s)
    assert stats.category_seconds is not None

    active_bursts: list[float] = []
    current_burst = 0.0

    for event in events:
        if isinstance(event, AppActivityEvent):
            dur = float(event.duration_s)
            stats.total_active_s += dur
            if event.aligned:
                stats.aligned_active_s += dur
            key = event.app_category.value
            stats.category_seconds[key] = stats.category_seconds.get(key, 0.0) + dur
            if dur > 0:
                current_burst += dur
        elif isinstance(event, ContextSwitchEvent):
            if current_burst > 0:
                active_bursts.append(current_burst)
                current_burst = 0.0
            weight = 1.0
            if event.from_aligned and event.to_aligned:
                weight = config.aligned_switch_penalty
            stats.weighted_switches += weight
        elif isinstance(event, IdleStateEvent):
            if current_burst > 0:
                active_bursts.append(current_burst)
                current_burst = 0.0
            if event.is_idle:
                stats.total_idle_s += float(event.duration_s)
                if event.duration_s >= config.idle_threshold_s:
                    stats.n_idle += 1
        elif isinstance(event, AttentionProbeEvent):
            if stats.latest_probe is None or event.timestamp >= stats.latest_probe.timestamp:
                stats.latest_probe = event

    if current_burst > 0:
        active_bursts.append(current_burst)
    stats.n_short = sum(1 for b in active_bursts if b < config.short_burst_s)
    return stats


def score_alignment(stats: WindowStats) -> float | None:
    if stats.total_active_s <= 0:
        return None
    return _clamp(stats.aligned_active_s / stats.total_active_s)


def score_switch(stats: WindowStats, config: FocusIndexConfig) -> float | None:
    if stats.total_active_s <= 0:
        return None
    active_minutes = max(stats.total_active_s / 60.0, 1e-6)
    raw = stats.weighted_switches / active_minutes
    return _clamp(1.0 - raw / config.switch_rate_ref)


def score_idle(stats: WindowStats, config: FocusIndexConfig) -> float | None:
    # No observed active or idle intervals → component unavailable.
    if stats.total_active_s <= 0 and stats.total_idle_s <= 0:
        return None
    idle_frac = stats.total_idle_s / stats.window_s
    value = 1.0
    value -= 0.35 * min(stats.n_idle / 4.0, 1.0)
    value -= 0.35 * min(idle_frac / 0.5, 1.0)
    value -= 0.30 * min(stats.n_short / 4.0, 1.0)
    return _clamp(value)


def score_probe(
    probe: AttentionProbeEvent | None,
    *,
    now: datetime,
    config: FocusIndexConfig,
) -> float | None:
    if probe is None:
        return None
    ttl = timedelta(minutes=config.probe_ttl_minutes)
    ts = probe.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if now - ts > ttl:
        return None

    acc = _clamp(probe.accuracy)
    omission_control = _clamp(1.0 - probe.omission_rate)
    commission_control = _clamp(1.0 - probe.commission_rate)
    if probe.rt_mean_ms <= 1e-6:
        rt_consistency = 0.0
    else:
        rt_cv = probe.rt_std_ms / probe.rt_mean_ms
        rt_consistency = _clamp(1.0 - rt_cv / config.rt_cv_ref)
    p = (
        0.4 * acc
        + 0.2 * omission_control
        + 0.2 * commission_control
        + 0.2 * rt_consistency
    )
    if probe.self_rating is not None:
        # Map 1–7 → slight ±0.05 nudge around mid (4).
        nudge = ((probe.self_rating - 4) / 3.0) * 0.05
        p = _clamp(p + nudge)
    return _clamp(p)


def weighted_sum(
    components: ComponentScores, config: FocusIndexConfig
) -> float | None:
    """Return W in [0,1] or None if no components available."""
    weights = config.weights
    pairs: list[tuple[float, float]] = []
    for key, weight in weights.items():
        value = getattr(components, key)
        if value is not None:
            pairs.append((float(value), float(weight)))
    if not pairs:
        return None
    total_w = sum(w for _, w in pairs)
    if total_w <= 0:
        return None
    return sum(v * (w / total_w) for v, w in pairs)


def combine_focus(
    measured: float | None, pattern_similarity: float | None
) -> tuple[float | None, float | None, FocusSource | None]:
    """Return (focus_index, pattern_focus, source) using max(measured, pattern)."""
    pattern_focus = None if pattern_similarity is None else 100.0 * pattern_similarity
    if measured is None and pattern_focus is None:
        return None, None, None
    if measured is None:
        return pattern_focus, pattern_focus, FocusSource.PATTERN_SIMILARITY
    if pattern_focus is None:
        return measured, None, FocusSource.MEASURED
    if abs(measured - pattern_focus) < 1e-9:
        return measured, pattern_focus, FocusSource.TIE
    if measured >= pattern_focus:
        return measured, pattern_focus, FocusSource.MEASURED
    return pattern_focus, pattern_focus, FocusSource.PATTERN_SIMILARITY


def band_for(focus_index: float | None, config: FocusIndexConfig) -> FocusBand:
    if focus_index is None:
        return FocusBand.UNCERTAIN
    if focus_index < config.band_low:
        return FocusBand.LOW
    if focus_index < config.band_moderate:
        return FocusBand.MODERATE
    if focus_index < config.band_high:
        return FocusBand.HIGH
    return FocusBand.VERY_HIGH


def confidence_from_components(components: ComponentScores) -> float:
    present = sum(
        1 for key in ("A", "S", "I", "P") if getattr(components, key) is not None
    )
    return present / 4.0


def score_window(
    events: Iterable[FocusEvent],
    *,
    window_start: datetime,
    window_end: datetime,
    config: FocusIndexConfig,
    pattern_similarity: float | None = None,
    baseline_status: FocusStatus | None = None,
) -> FocusIndexResult:
    event_list = list(events)
    stats = accumulate_stats(
        event_list, window_start=window_start, window_end=window_end, config=config
    )
    components = ComponentScores(
        A=score_alignment(stats),
        S=score_switch(stats, config),
        I=score_idle(stats, config),
        P=score_probe(stats.latest_probe, now=window_end, config=config),
    )
    w = weighted_sum(components, config)
    measured = None if w is None else 100.0 * w
    focus_index, pattern_focus, source = combine_focus(measured, pattern_similarity)

    uncertainties: list[str] = []
    idle_frac = stats.total_idle_s / stats.window_s
    low_active = stats.total_active_s < config.low_active_uncertain_s and idle_frac > 0.4

    status = FocusStatus.OK
    band = band_for(focus_index, config)
    if focus_index is None:
        status = FocusStatus.INSUFFICIENT
        band = FocusBand.UNCERTAIN
        uncertainties.append("no_measured_or_pattern_signal")
    elif low_active:
        status = FocusStatus.UNCERTAIN
        band = FocusBand.UNCERTAIN
        uncertainties.append("high_idle_low_active")
    elif baseline_status == FocusStatus.CALIBRATING:
        status = FocusStatus.CALIBRATING
        uncertainties.append("baseline_calibrating")

    if components.P is None:
        uncertainties.append("probe_missing_or_expired")

    return FocusIndexResult(
        focus_index=focus_index,
        measured_focus=measured,
        pattern_similarity=pattern_similarity,
        pattern_focus=pattern_focus,
        focus_source=source,
        focus_band=band,
        status=status,
        confidence=confidence_from_components(components),
        components=components,
        window_start=window_start,
        window_end=window_end,
        uncertainties=uncertainties,
        extras={
            "aligned_active_s": stats.aligned_active_s,
            "total_active_s": stats.total_active_s,
            "weighted_switches": stats.weighted_switches,
            "total_idle_s": stats.total_idle_s,
            "n_idle": stats.n_idle,
            "n_short": stats.n_short,
            "category_seconds": dict(stats.category_seconds or {}),
        },
    )

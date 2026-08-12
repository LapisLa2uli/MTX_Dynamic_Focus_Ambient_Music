"""Personal baseline helpers (median / IQR) for FLI aggregates."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from adaptive_soundscape.focus_index.config import FocusIndexConfig
from adaptive_soundscape.focus_index.models import FocusStatus
from adaptive_soundscape.focus_index.storage import FocusIndexStorage


@dataclass
class BaselineSummary:
    status: FocusStatus
    sample_count: int
    median: float | None = None
    iqr: float | None = None
    q1: float | None = None
    q3: float | None = None


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        raise ValueError("empty")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def summarize_baseline(
    values: list[float], config: FocusIndexConfig
) -> BaselineSummary:
    if len(values) < config.min_baseline_windows:
        return BaselineSummary(
            status=FocusStatus.CALIBRATING, sample_count=len(values)
        )
    ordered = sorted(values)
    q1 = _percentile(ordered, 0.25)
    q3 = _percentile(ordered, 0.75)
    return BaselineSummary(
        status=FocusStatus.OK,
        sample_count=len(values),
        median=float(median(ordered)),
        iqr=float(q3 - q1),
        q1=q1,
        q3=q3,
    )


def baseline_for_profile(
    storage: FocusIndexStorage, task_profile: str, config: FocusIndexConfig
) -> BaselineSummary:
    return summarize_baseline(storage.load_focus_values(task_profile), config)

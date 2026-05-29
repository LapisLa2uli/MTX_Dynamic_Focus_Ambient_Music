"""Derived activity metrics from raw signals."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivityMetrics:
    input_rate: float
    switch_rate: float
    idle_ratio: float
    cpu_load: float


def compute_metrics(
    *,
    keystrokes: int,
    clicks: int,
    scrolls: int,
    idle_seconds: float,
    cpu_percent: float,
    window_switches: int,
    interval_seconds: float,
) -> ActivityMetrics:
    """Compute normalized activity metrics for cognitive estimation."""
    interval = max(interval_seconds, 0.001)
    input_events = keystrokes + clicks + scrolls
    input_rate = min(1.0, input_events / (interval * 8.0))
    switch_rate = min(1.0, window_switches / max(interval / 10.0, 1.0))
    idle_ratio = min(1.0, idle_seconds / max(interval * 3.0, 1.0))
    cpu_load = min(1.0, cpu_percent / 100.0)
    return ActivityMetrics(
        input_rate=input_rate,
        switch_rate=switch_rate,
        idle_ratio=idle_ratio,
        cpu_load=cpu_load,
    )

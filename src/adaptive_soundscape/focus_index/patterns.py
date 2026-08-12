"""Calibration pattern vectors and cosine similarity."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from adaptive_soundscape.focus_index.config import FocusIndexConfig
from adaptive_soundscape.focus_index.models import AppCategory, FocusEvent
from adaptive_soundscape.focus_index.scoring import WindowStats, accumulate_stats, score_probe


FEATURE_KEYS: tuple[str, ...] = (
    "aligned_active_ratio",
    "switches_per_active_min",
    "idle_frac",
    "idle_event_rate",
    "short_burst_rate",
    "probe_score",
) + tuple(f"cat_{c.value}" for c in AppCategory)


def build_feature_vector(
    stats: WindowStats,
    *,
    config: FocusIndexConfig,
    window_end=None,
) -> dict[str, float]:
    total_active = max(stats.total_active_s, 1e-6)
    active_minutes = max(stats.total_active_s / 60.0, 1e-6)
    window_s = max(stats.window_s, 1e-6)
    cat = stats.category_seconds or {}
    cat_total = sum(cat.values()) or 1e-6

    probe = None
    if window_end is not None:
        probe = score_probe(stats.latest_probe, now=window_end, config=config)
    elif stats.latest_probe is not None:
        from datetime import datetime, timezone

        probe = score_probe(
            stats.latest_probe,
            now=stats.latest_probe.timestamp
            if stats.latest_probe.timestamp.tzinfo
            else stats.latest_probe.timestamp.replace(tzinfo=timezone.utc),
            config=config,
        )

    features: dict[str, float] = {
        "aligned_active_ratio": stats.aligned_active_s / total_active
        if stats.total_active_s > 0
        else 0.0,
        "switches_per_active_min": stats.weighted_switches / active_minutes
        if stats.total_active_s > 0
        else 0.0,
        "idle_frac": stats.total_idle_s / window_s,
        "idle_event_rate": stats.n_idle / (window_s / 60.0),
        "short_burst_rate": stats.n_short / max(len(cat) or 1, 1),
        "probe_score": float(probe) if probe is not None else 0.0,
    }
    for category in AppCategory:
        key = f"cat_{category.value}"
        features[key] = float(cat.get(category.value, 0.0)) / cat_total
    return features


def vector_from_events(
    events: Iterable[FocusEvent],
    *,
    window_start,
    window_end,
    config: FocusIndexConfig,
) -> dict[str, float]:
    stats = accumulate_stats(
        events, window_start=window_start, window_end=window_end, config=config
    )
    return build_feature_vector(stats, config=config, window_end=window_end)


def _as_ordered(features: Mapping[str, float]) -> list[float]:
    return [float(features.get(k, 0.0)) for k in FEATURE_KEYS]


def cosine_similarity(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    va = _as_ordered(a)
    vb = _as_ordered(b)
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(y * y for y in vb))
    if na <= 1e-12 or nb <= 1e-12:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def max_similarity(
    current: Mapping[str, float],
    patterns: Sequence[Mapping[str, Any]],
) -> float | None:
    if not patterns:
        return None
    best = 0.0
    found = False
    for pattern in patterns:
        features = pattern.get("features") if isinstance(pattern, Mapping) else None
        if not isinstance(features, Mapping):
            # Allow raw feature dicts.
            features = pattern if all(isinstance(k, str) for k in pattern) else None
        if not isinstance(features, Mapping):
            continue
        best = max(best, cosine_similarity(current, features))
        found = True
    return best if found else None

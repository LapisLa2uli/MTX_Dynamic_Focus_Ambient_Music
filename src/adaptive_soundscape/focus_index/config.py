"""Configuration for Focus Likelihood Index scoring and retention."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def default_db_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "focus_index.sqlite"


@dataclass
class FocusIndexConfig:
    """Tunable FLI weights, thresholds, and retention."""

    weight_alignment: float = 0.40
    weight_switch: float = 0.30
    weight_idle: float = 0.20
    weight_probe: float = 0.10

    window_seconds: float = 180.0
    aligned_switch_penalty: float = 0.2
    switch_rate_ref: float = 1.25  # switches/active-minute → S=0

    idle_threshold_s: float = 45.0
    short_burst_s: float = 45.0
    low_active_uncertain_s: float = 60.0

    probe_ttl_minutes: float = 45.0
    rt_cv_ref: float = 0.35

    min_baseline_windows: int = 10
    retention_days: int = 7

    band_low: float = 40.0
    band_moderate: float = 60.0
    band_high: float = 80.0

    # Recency decay for live scoring (seconds). Smaller → snappier distraction response.
    recency_tau_seconds: float = 45.0
    # Pattern may only assist when measured ≥ gate; lift capped at assist_max points.
    pattern_gate_low: float = 55.0
    pattern_assist_max: float = 8.0

    db_path: Path = field(default_factory=default_db_path)

    @property
    def weights(self) -> dict[str, float]:
        return {
            "A": self.weight_alignment,
            "S": self.weight_switch,
            "I": self.weight_idle,
            "P": self.weight_probe,
        }

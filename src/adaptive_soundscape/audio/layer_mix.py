"""Focus-score → per-layer gain curves for layered stem mixing."""

from __future__ import annotations

from dataclasses import dataclass, field


LAYER_IDS: tuple[str, ...] = (
    "pad",
    "harmony",
    "melody_a",
    "rhythm",
    "melody_b",
    "texture",
    "recovery",
)

BASE_LAYER_IDS: tuple[str, ...] = ("pad", "harmony", "melody_a", "rhythm")
GENERATED_LAYER_IDS: tuple[str, ...] = ("melody_b", "texture")


@dataclass
class LayerCurve:
    """Piecewise-linear gain breakpoints: list of (score, gain)."""

    points: list[tuple[float, float]] = field(default_factory=list)

    def sample(self, score: float) -> float:
        if not self.points:
            return 0.0
        s = max(0.0, min(1.0, score))
        pts = sorted(self.points, key=lambda p: p[0])
        if s <= pts[0][0]:
            return max(0.0, min(1.0, pts[0][1]))
        if s >= pts[-1][0]:
            return max(0.0, min(1.0, pts[-1][1]))
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            if x0 <= s <= x1:
                if x1 <= x0:
                    return y1
                t = (s - x0) / (x1 - x0)
                return max(0.0, min(1.0, y0 + t * (y1 - y0)))
        return pts[-1][1]


def default_layer_curves() -> dict[str, LayerCurve]:
    return {
        "pad": LayerCurve([(0.0, 0.70), (0.4, 0.80), (0.7, 0.65), (1.0, 0.55)]),
        "harmony": LayerCurve([(0.0, 0.25), (0.4, 0.70), (0.7, 0.85), (1.0, 0.75)]),
        "melody_a": LayerCurve([(0.0, 0.00), (0.4, 0.45), (0.7, 0.90), (1.0, 0.85)]),
        "rhythm": LayerCurve([(0.0, 0.35), (0.4, 0.55), (0.7, 0.25), (1.0, 0.10)]),
        "melody_b": LayerCurve([(0.0, 0.00), (0.4, 0.00), (0.7, 0.55), (1.0, 0.80)]),
        "texture": LayerCurve([(0.0, 0.00), (0.4, 0.10), (0.7, 0.40), (1.0, 0.60)]),
        "recovery": LayerCurve([(0.0, 0.00), (1.0, 0.00)]),
    }


@dataclass
class LayerMixConfig:
    curves: dict[str, LayerCurve] = field(default_factory=default_layer_curves)
    gain_slew_seconds: float = 1.25
    energy_limit: float = 1.35
    recovery_peak: float = 0.55
    recovery_seconds: float = 10.0


def compute_layer_gains(
    score: float,
    *,
    available: set[str] | frozenset[str],
    config: LayerMixConfig | None = None,
    recovery_active: bool = False,
) -> dict[str, float]:
    """Sample gain curves for available layers; optionally boost recovery."""
    cfg = config or LayerMixConfig()
    gains: dict[str, float] = {}
    for layer_id in LAYER_IDS:
        if layer_id not in available:
            continue
        curve = cfg.curves.get(layer_id) or LayerCurve([(0.0, 0.0), (1.0, 0.0)])
        gains[layer_id] = curve.sample(score)
    if recovery_active and "recovery" in available:
        gains["recovery"] = max(gains.get("recovery", 0.0), cfg.recovery_peak)
    return limit_energy(gains, cfg.energy_limit)


def limit_energy(gains: dict[str, float], limit: float = 1.35) -> dict[str, float]:
    """Soft-cap summed gains so stacked layers do not clip as easily."""
    total = sum(max(0.0, g) for g in gains.values())
    if total <= limit or total <= 1e-6:
        return {k: max(0.0, min(1.0, v)) for k, v in gains.items()}
    scale = limit / total
    return {k: max(0.0, min(1.0, v * scale)) for k, v in gains.items()}


def curves_from_mapping(raw: dict[str, list[list[float]]] | None) -> dict[str, LayerCurve]:
    """Build curves from YAML-like ``{layer: [[score, gain], ...]}``."""
    base = default_layer_curves()
    if not raw:
        return base
    for key, points in raw.items():
        if not points:
            continue
        parsed: list[tuple[float, float]] = []
        for pair in points:
            if len(pair) >= 2:
                parsed.append((float(pair[0]), float(pair[1])))
        if parsed:
            base[str(key)] = LayerCurve(parsed)
    return base

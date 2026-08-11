"""Tests for focus → layer gain curves."""

from adaptive_soundscape.audio.layer_mix import (
    LayerCurve,
    LayerMixConfig,
    compute_layer_gains,
    limit_energy,
)


def test_curve_interpolation():
    curve = LayerCurve([(0.0, 0.0), (1.0, 1.0)])
    assert abs(curve.sample(0.5) - 0.5) < 1e-6


def test_high_focus_raises_melody_lowers_rhythm():
    available = {"pad", "harmony", "melody_a", "rhythm", "melody_b", "texture"}
    low = compute_layer_gains(0.15, available=available)
    high = compute_layer_gains(0.9, available=available)
    assert high["melody_a"] > low["melody_a"]
    assert high["rhythm"] < low["rhythm"]
    assert high["melody_b"] > low["melody_b"]
    assert low["melody_b"] < 0.05
    assert high["melody_b"] > 0.2


def test_energy_limiter():
    gains = {"a": 1.0, "b": 1.0, "c": 1.0}
    limited = limit_energy(gains, limit=1.5)
    assert abs(sum(limited.values()) - 1.5) < 1e-6


def test_recovery_boost():
    available = {"pad", "recovery"}
    cfg = LayerMixConfig(recovery_peak=0.55)
    gains = compute_layer_gains(
        0.5, available=available, config=cfg, recovery_active=True
    )
    assert gains["recovery"] >= 0.55

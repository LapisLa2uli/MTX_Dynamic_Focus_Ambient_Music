"""Tests for focus → layer gain curves."""

from adaptive_soundscape.audio.layer_mix import (
    LayerCurve,
    LayerMixConfig,
    apply_break_melody,
    compute_layer_gains,
    limit_energy,
)


def test_curve_interpolation():
    curve = LayerCurve([(0.0, 0.0), (1.0, 1.0)])
    assert abs(curve.sample(0.5) - 0.5) < 1e-6


def test_high_focus_raises_melody_lowers_rhythm():
    available = {"pad", "harmony", "melody_a", "rhythm", "melody_b", "texture"}
    low = compute_layer_gains(0.15, available=available)
    mid = compute_layer_gains(0.5, available=available)
    high = compute_layer_gains(0.8, available=available)
    deep = compute_layer_gains(0.95, available=available)
    assert mid["melody_a"] == 0.0
    assert high["melody_a"] >= 0.95
    assert high["rhythm"] < low["rhythm"]
    assert high["melody_b"] == 0.0
    assert high["texture"] == 0.0
    assert deep["melody_b"] > 0.2
    assert deep["texture"] > 0.2


def test_melody_a_ramps_between_50_and_80():
    available = {"melody_a"}
    assert compute_layer_gains(0.5, available=available)["melody_a"] == 0.0
    mid = compute_layer_gains(0.65, available=available)["melody_a"]
    assert 0.4 < mid < 0.6
    assert abs(compute_layer_gains(0.8, available=available)["melody_a"] - 1.0) < 1e-6


def test_melody_b_texture_start_at_90():
    available = {"melody_b", "texture"}
    assert compute_layer_gains(0.899, available=available)["melody_b"] == 0.0
    assert compute_layer_gains(0.899, available=available)["texture"] == 0.0
    at_90 = compute_layer_gains(0.9, available=available)
    assert at_90["melody_b"] >= 0.5
    assert at_90["texture"] >= 0.35
    top = compute_layer_gains(1.0, available=available)
    assert top["melody_b"] > 0.7
    assert top["texture"] > 0.5


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


def test_break_melody_forces_melody_a_full():
    available = {"pad", "harmony", "melody_a", "rhythm"}
    low = compute_layer_gains(0.15, available=available)
    assert low["melody_a"] == 0.0
    forced = apply_break_melody(low)
    assert forced["melody_a"] == 1.0
    assert forced["pad"] == low["pad"]
    skipped = apply_break_melody({"pad": 0.7})
    assert "melody_a" not in skipped
    assert skipped["pad"] == 0.7

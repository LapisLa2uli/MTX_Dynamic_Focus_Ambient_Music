"""Tests for PlaceholderMixer crossfade continuity (no audio device)."""

from __future__ import annotations

import math
import threading
import wave
from pathlib import Path

import numpy as np
import pytest

from adaptive_soundscape.audio.parameters import AudioParameters
from adaptive_soundscape.audio.placeholder_mixer import PlaceholderMixer


def _write_constant_wav(path: Path, value: float, seconds: float = 1.0, rate: int = 44100) -> None:
    samples = (np.full(int(rate * seconds), value, dtype=np.float32) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())


@pytest.fixture
def assets_dir(tmp_path: Path) -> Path:
    _write_constant_wav(tmp_path / "programming" / "programming_01.wav", 0.5, seconds=2.0)
    _write_constant_wav(tmp_path / "scientific" / "scientific_01.wav", 0.4, seconds=2.0)
    return tmp_path


def test_equal_power_weights_preserve_power_at_midpoint():
    gain_a, gain_b = PlaceholderMixer._equal_power_weights(0.5)
    assert gain_a == pytest.approx(math.sqrt(0.5), rel=1e-6)
    assert gain_b == pytest.approx(math.sqrt(0.5), rel=1e-6)
    # Uncorrelated unit-energy sources: combined power ≈ gain_a^2 + gain_b^2 ≈ 1
    assert gain_a**2 + gain_b**2 == pytest.approx(1.0, rel=1e-6)


def test_equal_power_endpoints():
    assert PlaceholderMixer._equal_power_weights(0.0) == pytest.approx((1.0, 0.0))
    assert PlaceholderMixer._equal_power_weights(1.0) == pytest.approx((0.0, 1.0))


def test_crossfade_decode_does_not_hold_lock(assets_dir: Path):
    mixer = PlaceholderMixer(assets_dir, prefer_mp3=False)
    mixer._ensure_buffers("programming")
    mixer._profile_id = "programming"

    decode_started = threading.Event()
    lock_acquired_during_decode = threading.Event()
    release_decode = threading.Event()
    original_load = mixer._load_track

    def slow_load(track: Path):
        decode_started.set()
        # Prove the audio lock is free while decoding.
        if mixer._lock.acquire(timeout=0.5):
            lock_acquired_during_decode.set()
            mixer._lock.release()
        release_decode.wait(timeout=2.0)
        return original_load(track)

    mixer._load_track = slow_load  # type: ignore[method-assign]

    def run_crossfade() -> None:
        mixer.crossfade_to("scientific", 1.0, AudioParameters(0.5, 0.4, 0.55))

    thread = threading.Thread(target=run_crossfade)
    thread.start()
    assert decode_started.wait(timeout=2.0)
    assert lock_acquired_during_decode.wait(timeout=2.0)
    release_decode.set()
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert mixer._target_profile_id == "scientific"
    assert mixer._crossfade_remaining > 0


def test_incoming_buffer_playhead_skips_edge_fade(assets_dir: Path):
    mixer = PlaceholderMixer(assets_dir, sample_rate=44100, prefer_mp3=False)
    mixer._ensure_buffers("scientific")
    pos = mixer._positions["scientific"]
    buf_len = len(mixer._buffers["scientific"])
    expected = min(44100 // 2, buf_len // 16)
    assert expected > 0
    assert pos == expected
    assert pos != 0


def test_render_equal_power_mid_crossfade_keeps_energy(assets_dir: Path):
    mixer = PlaceholderMixer(assets_dir, sample_rate=44100, prefer_mp3=False, master_volume=1.0)
    # Unit buffers so mix energy is predictable.
    length = 44100
    mixer._buffers["programming"] = np.ones(length, dtype=np.float32)
    mixer._buffers["scientific"] = np.ones(length, dtype=np.float32)
    mixer._positions["programming"] = 0
    mixer._positions["scientific"] = 0
    mixer._profile_id = "programming"
    mixer._target_profile_id = "scientific"
    mixer._params = AudioParameters(0.5, 0.5, 0.5)
    mixer._target_params = AudioParameters(0.5, 0.5, 0.5)
    mixer._crossfade_total = 1000
    mixer._crossfade_remaining = 500  # t = 0.5

    block = mixer._render(64)
    # With equal-power and identical unit signals after param shaping, amplitude ≈ shape * (a+b)
    # shape for params(0.5,0.5,0.5): energy=0.5, brightness factor=1.0, warmth=0.975 → 0.4875
    # gains a=b=√0.5, sum ≈ √2 → sample ≈ 0.4875 * √2 ≈ 0.69
    assert float(np.mean(np.abs(block))) > 0.4
    # Linear equal-gain would use 0.5+0.5=1.0 of shaped; equal-power uses √2 ≈ 1.414 of each
    # path contribution in amplitude for correlated sources — key is no near-silence.
    assert float(np.min(np.abs(block))) > 0.3


def test_muted_stem_playhead_stays_phase_locked(assets_dir: Path):
    """Silent layers must keep advancing so unmute does not restart mid-phrase."""
    mixer = PlaceholderMixer(assets_dir, sample_rate=44100, prefer_mp3=False, master_volume=1.0)
    length = 44100
    mixer._stem_mode = True
    mixer._stem_buffers = {
        "harmony": np.linspace(0, 1, length, dtype=np.float32),
        "melody_a": np.linspace(0, 1, length, dtype=np.float32),
    }
    mixer._stem_positions = {"harmony": 100, "melody_a": 100}
    mixer._stem_gains = {"harmony": 0.8, "melody_a": 0.0}
    mixer._stem_gain_targets = dict(mixer._stem_gains)
    mixer._stem_slew_remaining = 0
    mixer._params = AudioParameters(0.5, 0.5, 0.5)
    mixer._profile_id = "__stem__"
    mixer._target_profile_id = "__stem__"

    frames = 256
    mixer._render(frames)
    assert mixer._stem_positions["harmony"] == 100 + frames
    assert mixer._stem_positions["melody_a"] == 100 + frames

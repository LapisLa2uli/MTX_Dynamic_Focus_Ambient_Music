"""Tests for muffling parameter and mixer low-pass."""

from __future__ import annotations

import numpy as np
import pytest

from adaptive_soundscape.audio.parameters import AudioParameters
from adaptive_soundscape.audio.placeholder_mixer import PlaceholderMixer
from adaptive_soundscape.session.pomodoro import PomodoroController


def test_audio_parameters_with_muffling():
    p = AudioParameters(0.5, 0.4, 0.55)
    assert p.muffling == 0.0
    q = p.with_muffling(0.7)
    assert q.muffling == 0.7
    assert q.brightness == p.brightness


def test_mixer_muffle_reduces_high_frequency_energy(tmp_path):
    mixer = PlaceholderMixer(tmp_path, sample_rate=44100, block_size=1024)
    # High-frequency alternating signal.
    n = 2048
    block = np.ones(n, dtype=np.float32)
    block[1::2] = -1.0
    clear = mixer._apply_params(block.copy(), AudioParameters(0.5, 1.0, 0.5, 0.0))
    muffled = mixer._apply_params(block.copy(), AudioParameters(0.5, 1.0, 0.5, 1.0))
    # Muffled output should have lower sample-to-sample energy (smoother).
    clear_diff = float(np.mean(np.abs(np.diff(clear))))
    muff_diff = float(np.mean(np.abs(np.diff(muffled))))
    assert muff_diff < clear_diff


def test_pomodoro_break_muffling_override():
    pomo = PomodoroController(work_minutes=0.001, break_minutes=25, break_muffling=0.9)
    pomo.start_work("programming")
    # Force break.
    pomo.start_break()
    assert pomo.muffling_override() == 0.9
    pomo.cancel()
    assert pomo.muffling_override() is None


def test_break_cutoff_is_ten_times_lower():
    from adaptive_soundscape.audio.placeholder_mixer import muffle_cutoff_hz

    work = muffle_cutoff_hz(0.85)
    brk = muffle_cutoff_hz(1.0 + 0.85)
    assert work / brk == pytest.approx(10.0, rel=0.02)
    assert brk < 200.0


def test_work_and_break_chimes_are_distinct():
    from adaptive_soundscape.audio.chimes import render_chime

    work = render_chime("work", 22050)
    brk = render_chime("break", 22050)
    n = min(len(work), len(brk))
    assert not np.allclose(work[:n], brk[:n], atol=1e-3)
    assert np.max(np.abs(work)) > 0.05
    assert np.max(np.abs(brk)) > 0.05

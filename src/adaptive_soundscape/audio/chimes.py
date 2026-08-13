"""Short synthesized notification chimes for Pomodoro phase changes."""

from __future__ import annotations

import logging
import math

import numpy as np

logger = logging.getLogger(__name__)

WORK_CHIME = "work"
BREAK_CHIME = "break"


def render_chime(kind: str, sample_rate: int = 44100) -> np.ndarray:
    """Return a mono float32 chime. Work is a bright rising pair; break is a lower fall."""
    if kind == BREAK_CHIME:
        return _tone_pair(
            sample_rate,
            freqs=(392.0, 294.0),  # G4 → D4, descending
            durs=(0.22, 0.38),
            gains=(0.38, 0.32),
            decay=(6.0, 4.2),
        )
    return _tone_pair(
        sample_rate,
        freqs=(659.3, 987.8),  # E5 → B5, rising
        durs=(0.14, 0.22),
        gains=(0.42, 0.36),
        decay=(9.0, 7.0),
    )


def _tone_pair(
    sample_rate: int,
    *,
    freqs: tuple[float, float],
    durs: tuple[float, float],
    gains: tuple[float, float],
    decay: tuple[float, float],
) -> np.ndarray:
    parts = [
        _pluck(sample_rate, freq, dur, gain, dec)
        for freq, dur, gain, dec in zip(freqs, durs, gains, decay)
    ]
    gap = np.zeros(int(sample_rate * 0.04), dtype=np.float32)
    return np.concatenate([parts[0], gap, parts[1]])


def _pluck(
    sample_rate: int, freq: float, seconds: float, gain: float, decay: float
) -> np.ndarray:
    n = max(1, int(sample_rate * seconds))
    t = np.arange(n, dtype=np.float32) / float(sample_rate)
    # Slight 2nd harmonic so the two chimes are easier to tell apart.
    wave = np.sin(2.0 * math.pi * freq * t) + 0.18 * np.sin(4.0 * math.pi * freq * t)
    env = np.exp(-decay * t).astype(np.float32)
    attack = min(int(sample_rate * 0.008), n)
    if attack > 1:
        env[:attack] *= np.linspace(0.0, 1.0, attack, dtype=np.float32)
    return (wave * env * gain).astype(np.float32)


def play_chime_standalone(kind: str, sample_rate: int = 44100) -> None:
    """Play through a one-shot stream when the main mixer is not running."""
    samples = render_chime(kind, sample_rate)
    try:
        import sounddevice as sd

        sd.play(samples, sample_rate, blocking=False)
    except Exception:
        logger.exception("Could not play Pomodoro %s chime", kind)

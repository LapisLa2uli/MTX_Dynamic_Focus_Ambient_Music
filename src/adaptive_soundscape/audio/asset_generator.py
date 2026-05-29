"""Generate placeholder ambient WAV loops for each context profile."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100
DURATION_SECONDS = 60

PROFILES: dict[str, tuple[float, float, float]] = {
    "programming": (110.0, 220.0, 0.08),
    "team_workflow": (130.0, 260.0, 0.07),
    "reading_writing": (98.0, 196.0, 0.06),
    "scientific": (117.0, 234.0, 0.075),
    "creative_design": (146.0, 292.0, 0.09),
    "distraction": (88.0, 176.0, 0.05),
    "unknown": (105.0, 210.0, 0.065),
}


def _render_pad(freq_a: float, freq_b: float, amplitude: float, seconds: float) -> np.ndarray:
    t = np.linspace(0, seconds, int(SAMPLE_RATE * seconds), endpoint=False)
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * t)
    tone_a = np.sin(2 * np.pi * freq_a * t)
    tone_b = 0.5 * np.sin(2 * np.pi * freq_b * t + 0.3)
    pad = (tone_a + tone_b) * amplitude * lfo
    fade = min(SAMPLE_RATE // 4, len(pad) // 8)
    pad[:fade] *= np.linspace(0, 1, fade)
    pad[-fade:] *= np.linspace(1, 0, fade)
    return np.clip(pad, -1.0, 1.0)


def write_wav(path: Path, samples: np.ndarray) -> None:
    pcm = (samples * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


def generate_all(assets_dir: Path) -> None:
    for profile_id, (fa, fb, amp) in PROFILES.items():
        samples = _render_pad(fa, fb, amp, DURATION_SECONDS)
        write_wav(assets_dir / f"{profile_id}.wav", samples)
        pad = _render_pad(fa * 0.5, fb * 0.5, amp * 0.6, DURATION_SECONDS)
        write_wav(assets_dir / f"{profile_id}_pad.wav", pad)

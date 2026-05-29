"""Generate placeholder ambient WAV loops for each context profile."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, filtfilt

from adaptive_soundscape.audio.loader import SUPPORTED_EXTENSIONS, load_audio_mono

SAMPLE_RATE = 44100
DURATION_SECONDS = 60
PAD_SAMPLE_RATE = 44100
PAD_GAIN = 0.58
PAD_LOWPASS_HZ = 900.0

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


def generate_all(assets_dir: Path, *, overwrite: bool = False) -> list[Path]:
    """Generate main loops and pad layers for every profile."""
    written: list[Path] = []
    written.extend(generate_mains(assets_dir, overwrite=overwrite))
    written.extend(generate_pads(assets_dir, overwrite=overwrite))
    return written


def generate_mains(assets_dir: Path, *, overwrite: bool = False) -> list[Path]:
    """Generate `{profile_id}.wav` main ambient loops."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for profile_id, (fa, fb, amp) in PROFILES.items():
        path = assets_dir / f"{profile_id}.wav"
        if path.exists() and not overwrite:
            continue
        samples = _render_pad(fa, fb, amp, DURATION_SECONDS)
        write_wav(path, samples)
        written.append(path)
    return written


def generate_pads(assets_dir: Path, *, overwrite: bool = False) -> list[Path]:
    """Generate pad underlayers from main audio, or synthetic placeholders if none exist."""
    if discover_main_assets(assets_dir):
        return generate_pads_from_sources(assets_dir, overwrite=overwrite)

    assets_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for profile_id, (fa, fb, amp) in PROFILES.items():
        path = assets_dir / f"{profile_id}_pad.wav"
        if path.exists() and not overwrite:
            continue
        pad = _render_pad(fa * 0.5, fb * 0.5, amp * 0.6, DURATION_SECONDS)
        write_wav(path, pad)
        written.append(path)
    return written


def discover_main_assets(assets_dir: Path) -> list[Path]:
    """Return main audio files in ``assets_dir`` (excluding existing pad stems)."""
    if not assets_dir.is_dir():
        return []
    mains: list[Path] = []
    for path in sorted(assets_dir.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if path.stem.endswith("_pad"):
            continue
        mains.append(path)
    return mains


def derive_pad_samples(samples: np.ndarray, sample_rate: int = PAD_SAMPLE_RATE) -> np.ndarray:
    """Create a softer, warmer underlayer from a main loop."""
    if len(samples) == 0:
        return samples.astype(np.float32)

    pad = samples.astype(np.float32) * PAD_GAIN
    nyquist = sample_rate / 2.0
    cutoff = min(PAD_LOWPASS_HZ, nyquist * 0.95)
    if cutoff > 40 and len(pad) > 24:
        b, a = butter(2, cutoff / nyquist, btype="low")
        pad = filtfilt(b, a, pad).astype(np.float32)

    fade = min(sample_rate // 2, len(pad) // 16)
    if fade > 1:
        pad[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        pad[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)

    return np.clip(pad, -1.0, 1.0)


def generate_pads_from_sources(assets_dir: Path, *, overwrite: bool = False) -> list[Path]:
    """Build `{stem}_pad.wav` files from each main asset in ``assets_dir``."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for main_path in discover_main_assets(assets_dir):
        pad_path = assets_dir / f"{main_path.stem}_pad.wav"
        if pad_path.exists() and not overwrite:
            continue
        samples = load_audio_mono(main_path, PAD_SAMPLE_RATE)
        pad = derive_pad_samples(samples, PAD_SAMPLE_RATE)
        write_wav(pad_path, pad)
        written.append(pad_path)
    return written


def ensure_assets(assets_dir: Path) -> list[Path]:
    """Create any missing main or pad WAV files without overwriting existing ones."""
    return generate_all(assets_dir, overwrite=False)

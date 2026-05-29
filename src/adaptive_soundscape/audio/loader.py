"""Load mono audio loops from WAV or MP3 assets."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SUPPORTED_EXTENSIONS: tuple[str, ...] = (".wav", ".mp3")


def resolve_asset(directory: Path, stem: str, *, prefer_mp3: bool = True) -> Path | None:
    """Return the best existing asset for ``stem`` with a supported extension."""
    extensions = (".mp3", ".wav") if prefer_mp3 else (".wav", ".mp3")
    for ext in extensions:
        candidate = directory / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def load_audio_mono(path: Path, sample_rate: int = 44100) -> np.ndarray:
    """Decode ``path`` to a mono float32 numpy array at ``sample_rate`` Hz."""
    ext = path.suffix.lower()
    if ext == ".wav":
        return _load_wav_mono(path, sample_rate)
    if ext == ".mp3":
        return _load_mp3_mono(path, sample_rate)
    raise ValueError(f"Unsupported audio format: {path.suffix}")


def _load_wav_mono(path: Path, sample_rate: int) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        if wf.getnchannels() > 1:
            data = data.reshape(-1, wf.getnchannels()).mean(axis=1)
        source_rate = wf.getframerate()
    return _resample_mono(data, source_rate, sample_rate)


def _load_mp3_mono(path: Path, sample_rate: int) -> np.ndarray:
    try:
        import miniaudio
    except ImportError as exc:
        raise ImportError(
            "MP3 playback requires the 'miniaudio' package. "
            "Install it with: pip install miniaudio"
        ) from exc

    decoded = miniaudio.decode_file(
        str(path),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=sample_rate,
    )
    samples = np.asarray(decoded.samples, dtype=np.int16).astype(np.float32) / 32768.0
    if decoded.nchannels > 1:
        samples = samples.reshape(-1, decoded.nchannels).mean(axis=1)
    return np.clip(samples, -1.0, 1.0)


def _resample_mono(data: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or len(data) <= 1:
        return data.astype(np.float32)
    x_old = np.linspace(0, 1, len(data))
    new_len = max(int(len(data) * target_rate / source_rate), 1)
    x_new = np.linspace(0, 1, new_len)
    return np.interp(x_new, x_old, data).astype(np.float32)

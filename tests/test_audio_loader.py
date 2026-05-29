"""Tests for WAV/MP3 asset resolution and loading."""

import wave
from pathlib import Path

import numpy as np
import pytest

from adaptive_soundscape.audio.loader import load_audio_mono, resolve_asset


def _write_sine_wav(path: Path, seconds: float = 0.25, rate: int = 44100) -> None:
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    samples = (0.2 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())


def test_resolve_asset_prefers_mp3_when_both_exist(tmp_path):
    _write_sine_wav(tmp_path / "programming.wav")
    (tmp_path / "programming.mp3").write_bytes(b"not-a-real-mp3")
    resolved = resolve_asset(tmp_path, "programming", prefer_mp3=True)
    assert resolved is not None
    assert resolved.suffix == ".mp3"


def test_resolve_asset_prefers_wav_when_configured(tmp_path):
    _write_sine_wav(tmp_path / "programming.wav")
    (tmp_path / "programming.mp3").write_bytes(b"not-a-real-mp3")
    resolved = resolve_asset(tmp_path, "programming", prefer_mp3=False)
    assert resolved is not None
    assert resolved.suffix == ".wav"


def test_resolve_asset_finds_mp3_when_wav_missing(tmp_path):
    (tmp_path / "reading_writing.mp3").write_bytes(b"fake")
    resolved = resolve_asset(tmp_path, "reading_writing")
    assert resolved is not None
    assert resolved.suffix == ".mp3"


def test_load_audio_mono_wav(tmp_path):
    path = tmp_path / "scientific.wav"
    _write_sine_wav(path)
    data = load_audio_mono(path, sample_rate=44100)
    assert data.dtype == np.float32
    assert len(data) > 0
    assert np.max(np.abs(data)) <= 1.0


def test_load_audio_mono_rejects_unknown_extension(tmp_path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"data")
    with pytest.raises(ValueError, match="Unsupported"):
        load_audio_mono(path)

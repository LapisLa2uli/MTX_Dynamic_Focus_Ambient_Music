"""Tests for audio backend factory."""

from pathlib import Path

from adaptive_soundscape.audio.factory import create_audio_backend
from adaptive_soundscape.audio.placeholder_mixer import PlaceholderMixer
from adaptive_soundscape.core.config import Settings


def test_factory_uses_placeholder_when_configured():
    settings = Settings()
    settings.audio.backend = "placeholder"
    backend = create_audio_backend(settings, Path("assets/audio"))
    assert isinstance(backend, PlaceholderMixer)


def test_factory_godot_falls_back_when_project_missing(tmp_path):
    settings = Settings()
    settings.audio.backend = "godot"
    settings.audio.godot_project = str(tmp_path / "missing")
    settings.audio.fallback_to_placeholder = True
    assets = tmp_path / "audio"
    assets.mkdir()
    backend = create_audio_backend(settings, assets)
    assert isinstance(backend, PlaceholderMixer)

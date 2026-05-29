"""Construct the configured audio backend."""

from __future__ import annotations

import logging
from pathlib import Path

from adaptive_soundscape.audio.backend import AudioBackend
from adaptive_soundscape.audio.godot_backend import GodotAudioBackend
from adaptive_soundscape.audio.placeholder_mixer import PlaceholderMixer
from adaptive_soundscape.core.config import Settings, _project_root

logger = logging.getLogger(__name__)


def create_audio_backend(settings: Settings, assets_dir: Path) -> AudioBackend:
    backend = settings.audio.backend.lower().strip()
    if backend == "godot":
        project = _resolve_godot_project(settings)
        if not (project / "project.godot").exists():
            if settings.audio.fallback_to_placeholder:
                logger.warning("Godot project missing at %s; using placeholder mixer.", project)
                return _placeholder(settings, assets_dir)
            raise FileNotFoundError(f"Godot project not found: {project / 'project.godot'}")
        try:
            return GodotAudioBackend(
                project_path=project,
                assets_dir=assets_dir,
                godot_executable=settings.audio.godot_executable or None,
                host=settings.audio.godot_host,
                port=settings.audio.godot_port,
                master_volume=settings.audio.master_volume,
                startup_timeout=settings.audio.godot_startup_timeout,
            )
        except Exception as exc:
            if settings.audio.fallback_to_placeholder:
                logger.warning("Godot backend unavailable (%s); using placeholder mixer.", exc)
                return _placeholder(settings, assets_dir)
            raise
    return _placeholder(settings, assets_dir)


def _placeholder(settings: Settings, assets_dir: Path) -> PlaceholderMixer:
    return PlaceholderMixer(
        assets_dir=assets_dir,
        sample_rate=settings.audio.sample_rate,
        block_size=settings.audio.block_size,
        master_volume=settings.audio.master_volume,
        prefer_mp3=settings.audio.prefer_mp3,
    )


def _resolve_godot_project(settings: Settings) -> Path:
    project = Path(settings.audio.godot_project)
    if project.is_absolute():
        return project
    return _project_root() / project

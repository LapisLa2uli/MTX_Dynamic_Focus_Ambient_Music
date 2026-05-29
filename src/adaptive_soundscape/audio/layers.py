"""Audio layer definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adaptive_soundscape.audio.loader import resolve_asset


@dataclass(frozen=True)
class AudioLayer:
    name: str
    file_path: Path
    base_gain: float = 0.5


def default_layers(
    assets_dir: Path, profile_id: str, *, prefer_mp3: bool = True
) -> tuple[AudioLayer, ...]:
    layers: list[AudioLayer] = []
    main = resolve_asset(assets_dir, profile_id, prefer_mp3=prefer_mp3)
    if main is not None:
        layers.append(AudioLayer("main", main, 0.6))
    pad = resolve_asset(assets_dir, f"{profile_id}_pad", prefer_mp3=prefer_mp3)
    if pad is not None:
        layers.append(AudioLayer("pad", pad, 0.35))
    return tuple(layers)

"""Audio layer definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AudioLayer:
    name: str
    file_path: Path
    base_gain: float = 0.5


def default_layers(assets_dir: Path, profile_id: str) -> tuple[AudioLayer, ...]:
    loop = assets_dir / f"{profile_id}.wav"
    pad = assets_dir / f"{profile_id}_pad.wav"
    layers: list[AudioLayer] = []
    if loop.exists():
        layers.append(AudioLayer("main", loop, 0.6))
    if pad.exists():
        layers.append(AudioLayer("pad", pad, 0.35))
    if not layers and loop.exists():
        layers.append(AudioLayer("main", loop, 0.6))
    return tuple(layers)

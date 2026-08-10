"""Audio layer definitions backed by scenario albums."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adaptive_soundscape.audio.album import pick_random_track


@dataclass(frozen=True)
class AudioLayer:
    name: str
    file_path: Path
    base_gain: float = 0.5


def default_layers(
    assets_dir: Path,
    profile_id: str,
    *,
    prefer_mp3: bool = True,
    track: Path | None = None,
) -> tuple[AudioLayer, ...]:
    """Return a single main layer from the scenario album (random if unspecified)."""
    del prefer_mp3  # albums store concrete files; preference applies at migration time
    chosen = track or pick_random_track(assets_dir, profile_id)
    if chosen is None:
        return ()
    return (AudioLayer("main", chosen, 0.75),)

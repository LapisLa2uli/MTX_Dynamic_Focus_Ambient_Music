"""AudioBackend protocol — Godot sidecar or placeholder mixer."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from adaptive_soundscape.audio.parameters import AudioParameters


class AudioBackend(Protocol):
    """Pluggable audio engine interface."""

    def start(self, profile_id: str | None = None) -> None: ...

    def stop(self) -> None: ...

    def set_profile(self, profile_id: str) -> None: ...

    def set_parameters(self, params: AudioParameters) -> None: ...

    def crossfade_to(
        self,
        profile_id: str,
        duration_seconds: float,
        params: AudioParameters | None = None,
    ) -> None: ...

    def crossfade_to_track(
        self,
        path: Path,
        duration_seconds: float,
        params: AudioParameters | None = None,
    ) -> None: ...

    def load_stem_pack(
        self,
        layers: dict[str, Path],
        crossfade_seconds: float = 0.0,
    ) -> None: ...

    def set_layer_gains(
        self,
        gains: dict[str, float],
        slew_seconds: float = 1.0,
    ) -> None: ...

    def set_master_volume(self, volume: float) -> None: ...

    @property
    def is_playing(self) -> bool: ...

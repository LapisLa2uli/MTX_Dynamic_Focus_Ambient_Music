"""AudioBackend protocol for future FMOD swap."""

from __future__ import annotations

from typing import Protocol

from adaptive_soundscape.audio.parameters import AudioParameters


class AudioBackend(Protocol):
    """Pluggable audio engine interface."""

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def set_profile(self, profile_id: str) -> None: ...

    def set_parameters(self, params: AudioParameters) -> None: ...

    def crossfade_to(self, profile_id: str, duration_seconds: float) -> None: ...

    @property
    def is_playing(self) -> bool: ...

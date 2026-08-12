"""Audio parameter model for adaptive mixing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioParameters:
    brightness: float
    energy: float
    warmth: float
    muffling: float = 0.0

    def lerp(self, other: "AudioParameters", t: float) -> "AudioParameters":
        t = max(0.0, min(1.0, t))
        return AudioParameters(
            brightness=self.brightness + (other.brightness - self.brightness) * t,
            energy=self.energy + (other.energy - self.energy) * t,
            warmth=self.warmth + (other.warmth - self.warmth) * t,
            muffling=self.muffling + (other.muffling - self.muffling) * t,
        )

    def with_muffling(self, muffling: float) -> "AudioParameters":
        return AudioParameters(
            brightness=self.brightness,
            energy=self.energy,
            warmth=self.warmth,
            muffling=max(0.0, min(1.0, float(muffling))),
        )

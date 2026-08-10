"""Placeholder numpy/sounddevice ambient mixer with per-scenario albums."""

from __future__ import annotations

import logging
import math
import threading
from pathlib import Path

import numpy as np

from adaptive_soundscape.audio.album import (
    PROFILE_IDS,
    list_tracks,
    pick_random_track,
)
from adaptive_soundscape.audio.loader import load_audio_mono
from adaptive_soundscape.audio.parameters import AudioParameters

logger = logging.getLogger(__name__)


class PlaceholderMixer:
    """Loop album tracks with parameter-driven EQ-ish shaping."""

    def __init__(
        self,
        assets_dir: Path,
        sample_rate: int = 44100,
        block_size: int = 1024,
        master_volume: float = 0.75,
        prefer_mp3: bool = True,
    ) -> None:
        self.assets_dir = assets_dir
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.master_volume = master_volume
        self.prefer_mp3 = prefer_mp3
        self._profile_id = "unknown"
        self._target_profile_id = "unknown"
        self._params = AudioParameters(0.5, 0.4, 0.55)
        self._target_params = self._params
        self._crossfade_remaining = 0
        self._crossfade_total = 1
        self._stream = None
        self._buffers: dict[str, np.ndarray] = {}
        self._positions: dict[str, int] = {}
        self._profile_track: dict[str, Path] = {}
        self._track_cache: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()
        self._playing = False
        self._preload_thread: threading.Thread | None = None

    @property
    def is_playing(self) -> bool:
        return self._playing

    def invalidate_caches(self) -> None:
        """Drop decoded audio after album edits so new tracks are picked up."""
        with self._lock:
            self._buffers.clear()
            self._positions.clear()
            self._profile_track.clear()
            self._track_cache.clear()

    def _edge_guard(self, length: int) -> int:
        """Skip baked loop-edge fades so incoming stems are not silent."""
        if length <= 1:
            return 0
        guard = min(self.sample_rate // 2, length // 16)
        if length <= 2 * guard:
            return 0
        return guard

    def _load_track(self, track: Path) -> np.ndarray | None:
        key = str(track.resolve())
        with self._lock:
            cached = self._track_cache.get(key)
        if cached is not None:
            return cached
        data = load_audio_mono(track, self.sample_rate)
        if len(data) == 0:
            return None
        scaled = np.clip(data * 0.75, -1.0, 1.0).astype(np.float32)
        with self._lock:
            self._track_cache[key] = scaled
        return scaled

    def _assign_random_track(self, profile_id: str, *, force_new: bool = False) -> Path | None:
        """Pick (and decode) a random album song for ``profile_id``."""
        with self._lock:
            current = self._profile_track.get(profile_id)
            already = profile_id in self._buffers
        if already and not force_new and current is not None:
            return current

        exclude = current if force_new else None
        track = pick_random_track(self.assets_dir, profile_id, exclude=exclude)
        if track is None:
            return None
        data = self._load_track(track)
        if data is None:
            return None
        with self._lock:
            self._buffers[profile_id] = data
            self._positions[profile_id] = self._edge_guard(len(data))
            self._profile_track[profile_id] = track
        return track

    def _ensure_buffers(self, profile_id: str) -> None:
        self._assign_random_track(profile_id, force_new=False)

    def _known_profile_ids(self) -> list[str]:
        ids = set(PROFILE_IDS)
        ids.add(self._profile_id)
        ids.add(self._target_profile_id)
        return sorted(ids)

    def _preload_remaining_profiles(self) -> None:
        for profile_id in self._known_profile_ids():
            if not self._playing:
                return
            with self._lock:
                if profile_id in self._buffers:
                    continue
            try:
                # Warm the track cache with every song so later random picks are fast.
                for track in list_tracks(self.assets_dir, profile_id):
                    if not self._playing:
                        return
                    self._load_track(track)
                self._assign_random_track(profile_id, force_new=False)
            except Exception:
                logger.exception("Failed to preload album for '%s'", profile_id)

    def _start_background_preload(self) -> None:
        if self._preload_thread is not None and self._preload_thread.is_alive():
            return
        self._preload_thread = threading.Thread(
            target=self._preload_remaining_profiles,
            name="placeholder-preload",
            daemon=True,
        )
        self._preload_thread.start()

    def start(self, profile_id: str | None = None) -> None:
        if self._playing:
            return
        if profile_id:
            self.set_profile(profile_id)
        self._assign_random_track(self._profile_id, force_new=True)
        if self._profile_id not in self._buffers:
            raise RuntimeError(
                f"No album tracks found for profile '{self._profile_id}' in "
                f"{self.assets_dir / self._profile_id}"
            )
        try:
            import sounddevice as sd

            device = sd.default.device[1]
            track = self._profile_track.get(self._profile_id)
            logger.info(
                "Starting placeholder audio on device %s track=%s",
                device,
                track.name if track else "?",
            )

            def callback(outdata, frames, _time_info, status):
                if status:
                    logger.warning("Audio callback status: %s", status)
                block = self._render(frames)
                outdata[:] = block.reshape(-1, 1)

            self._stream = sd.OutputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                channels=1,
                callback=callback,
            )
            self._stream.start()
            self._playing = True
            self._start_background_preload()
        except Exception as exc:
            self._playing = False
            self._stream = None
            raise RuntimeError(f"Could not open audio output device: {exc}") from exc

    def stop(self) -> None:
        self._playing = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def set_profile(self, profile_id: str) -> None:
        self._assign_random_track(profile_id, force_new=True)
        with self._lock:
            self._profile_id = profile_id
            self._target_profile_id = profile_id

    def set_parameters(self, params: AudioParameters) -> None:
        with self._lock:
            self._params = params
            if self._crossfade_remaining <= 0:
                self._target_params = params

    def crossfade_to(
        self,
        profile_id: str,
        duration_seconds: float,
        params: AudioParameters | None = None,
    ) -> None:
        with self._lock:
            switching_profile = profile_id != self._profile_id
        if switching_profile:
            # New scenario → random song from that album (avoid current if possible).
            self._assign_random_track(profile_id, force_new=True)
        else:
            self._ensure_buffers(profile_id)
        with self._lock:
            self._target_profile_id = profile_id
            self._crossfade_total = max(int(duration_seconds * self.sample_rate), 1)
            self._crossfade_remaining = self._crossfade_total
            if params is not None:
                self._target_params = params

    def _read_loop(self, profile_id: str, frames: int) -> np.ndarray:
        with self._lock:
            buf = self._buffers.get(profile_id)
            if buf is None or len(buf) == 0:
                return np.zeros(frames, dtype=np.float32)
            pos = self._positions.get(profile_id, 0)
            length = len(buf)
            buffer = buf
        out = np.zeros(frames, dtype=np.float32)
        for i in range(frames):
            out[i] = buffer[pos]
            pos = (pos + 1) % length
        with self._lock:
            if self._buffers.get(profile_id) is buffer:
                self._positions[profile_id] = pos
        return out

    def _apply_params(self, block: np.ndarray, params: AudioParameters) -> np.ndarray:
        brightness = 0.5 + (params.brightness - 0.5) * 0.4
        energy = 0.5 + (params.energy - 0.5) * 0.5
        warmth = params.warmth
        shaped = block * energy
        shaped = shaped * (0.85 + brightness * 0.3)
        shaped = shaped * (0.9 + warmth * 0.15)
        return np.clip(shaped, -1.0, 1.0)

    @staticmethod
    def _equal_power_weights(t: float) -> tuple[float, float]:
        """Return (current_gain, target_gain) for equal-power crossfade."""
        t = max(0.0, min(1.0, t))
        return math.cos(t * math.pi * 0.5), math.sin(t * math.pi * 0.5)

    def _render(self, frames: int) -> np.ndarray:
        with self._lock:
            profile = self._profile_id
            target = self._target_profile_id
            params = self._params
            target_params = self._target_params
            fade_rem = self._crossfade_remaining
            fade_total = self._crossfade_total

        current = self._read_loop(profile, frames)
        current = self._apply_params(current, params)

        if fade_rem > 0 and target != profile:
            t = 1.0 - (fade_rem / max(fade_total, 1))
            gain_a, gain_b = self._equal_power_weights(t)
            target_block = self._read_loop(target, frames)
            target_block = self._apply_params(target_block, target_params)
            mixed = current * gain_a + target_block * gain_b
            fade_rem -= frames
            if fade_rem <= 0:
                with self._lock:
                    self._profile_id = target
                    self._params = target_params
                    self._crossfade_remaining = 0
            else:
                with self._lock:
                    self._crossfade_remaining = fade_rem
            out = mixed
        else:
            out = current

        return (out * self.master_volume).astype(np.float32)

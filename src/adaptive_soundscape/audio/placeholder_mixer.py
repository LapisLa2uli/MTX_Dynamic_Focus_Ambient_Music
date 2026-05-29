"""Placeholder numpy/sounddevice ambient mixer."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np

from adaptive_soundscape.audio.layers import default_layers
from adaptive_soundscape.audio.loader import load_audio_mono
from adaptive_soundscape.audio.parameters import AudioParameters

logger = logging.getLogger(__name__)


class PlaceholderMixer:
    """Loop WAV/MP3 assets with parameter-driven EQ-ish shaping."""

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
        self._layers = default_layers(assets_dir, self._profile_id, prefer_mp3=prefer_mp3)
        self._lock = threading.Lock()
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return self._playing

    def _mix_profile_layers(self, profile_id: str) -> np.ndarray | None:
        layers = default_layers(self.assets_dir, profile_id, prefer_mp3=self.prefer_mp3)
        if not layers:
            return None
        mixed: np.ndarray | None = None
        for layer in layers:
            data = load_audio_mono(layer.file_path, self.sample_rate)
            if len(data) == 0:
                continue
            scaled = data * layer.base_gain
            if mixed is None:
                mixed = scaled
            else:
                length = min(len(mixed), len(scaled))
                mixed = mixed[:length] + scaled[:length]
        if mixed is None:
            return None
        return np.clip(mixed, -1.0, 1.0).astype(np.float32)

    def _ensure_buffers(self, profile_id: str) -> None:
        if profile_id in self._buffers:
            return
        data = self._mix_profile_layers(profile_id)
        if data is not None:
            self._buffers[profile_id] = data
            self._positions[profile_id] = 0

    def start(self, profile_id: str | None = None) -> None:
        if self._playing:
            return
        if profile_id:
            self.set_profile(profile_id)
        self._ensure_buffers(self._profile_id)
        if self._profile_id not in self._buffers:
            raise RuntimeError(
                f"No audio files found for profile '{self._profile_id}' in {self.assets_dir}"
            )
        try:
            import sounddevice as sd

            device = sd.default.device[1]
            logger.info("Starting placeholder audio on output device %s", device)

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
        with self._lock:
            self._profile_id = profile_id
            self._target_profile_id = profile_id
            self._ensure_buffers(profile_id)
            self._layers = default_layers(
                self.assets_dir, profile_id, prefer_mp3=self.prefer_mp3
            )

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
            self._target_profile_id = profile_id
            self._ensure_buffers(profile_id)
            self._crossfade_total = max(int(duration_seconds * self.sample_rate), 1)
            self._crossfade_remaining = self._crossfade_total
            if params is not None:
                self._target_params = params

    def _read_loop(self, profile_id: str, frames: int) -> np.ndarray:
        buf = self._buffers.get(profile_id)
        if buf is None or len(buf) == 0:
            return np.zeros(frames, dtype=np.float32)
        pos = self._positions.get(profile_id, 0)
        out = np.zeros(frames, dtype=np.float32)
        for i in range(frames):
            out[i] = buf[pos]
            pos = (pos + 1) % len(buf)
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
            target_block = self._read_loop(target, frames)
            target_block = self._apply_params(target_block, target_params)
            mixed = current * (1.0 - t) + target_block * t
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

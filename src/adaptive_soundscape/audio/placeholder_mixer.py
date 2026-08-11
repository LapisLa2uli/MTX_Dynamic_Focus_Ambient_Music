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
        # Layered stem pack state (additive mix).
        self._stem_mode = False
        self._stem_buffers: dict[str, np.ndarray] = {}
        self._stem_positions: dict[str, int] = {}
        self._stem_gains: dict[str, float] = {}
        self._stem_gain_targets: dict[str, float] = {}
        self._stem_slew_remaining = 0
        self._stem_slew_total = 1
        self._stem_target_buffers: dict[str, np.ndarray] = {}
        self._stem_target_positions: dict[str, int] = {}
        self._stem_pack_fade_remaining = 0
        self._stem_pack_fade_total = 1
        self._stem_pack_paths: dict[str, Path] = {}
        # Live EQ / level for HomePage ring.
        self._current_level: float = 0.0
        self._n_bands = 48
        self._band_edges: np.ndarray = _build_band_edges(
            self._n_bands, sample_rate, 40.0
        )
        self._current_bands: list[float] = [0.0] * self._n_bands


    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def current_level(self) -> float:
        """Last RMS amplitude (0–1), updated from the audio callback thread."""
        return self._current_level

    @property
    def current_bands(self) -> list[float]:
        """48 log-spaced frequency-band amplitudes (0–1)."""
        return list(self._current_bands)

    def invalidate_caches(self) -> None:
        """Drop decoded audio after album edits so new tracks are picked up."""
        with self._lock:
            self._buffers.clear()
            self._positions.clear()
            self._profile_track.clear()
            self._track_cache.clear()
            self._stem_buffers.clear()
            self._stem_positions.clear()
            self._stem_target_buffers.clear()
            self._stem_target_positions.clear()
            self._stem_pack_paths.clear()
            self._stem_pack_fade_remaining = 0
            self._stem_mode = False

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

    def set_master_volume(self, volume: float) -> None:
        self.master_volume = max(0.0, min(1.0, float(volume)))

    def load_stem_pack(
        self,
        layers: dict[str, Path],
        crossfade_seconds: float = 0.0,
    ) -> None:
        """Load a multi-layer stem pack and mix additively."""
        loaded: dict[str, np.ndarray] = {}
        resolved: dict[str, Path] = {}
        for layer_id, path in layers.items():
            if not path.is_file():
                logger.warning("load_stem_pack: missing %s → %s", layer_id, path)
                continue
            data = self._load_track(path)
            if data is None:
                logger.warning("load_stem_pack: decode failed %s", path)
                continue
            loaded[layer_id] = data
            resolved[layer_id] = path.resolve()
        if not loaded:
            logger.warning("load_stem_pack: no layers loaded")
            return
        with self._lock:
            # Same pack already playing — keep playheads; avoid dual-offset overlap.
            if (
                self._stem_mode
                and self._stem_buffers
                and set(self._stem_buffers.keys()) == set(loaded.keys())
                and self._stem_pack_paths == resolved
            ):
                for lid in loaded:
                    self._stem_gains.setdefault(lid, 0.0)
                    self._stem_gain_targets.setdefault(lid, self._stem_gains[lid])
                return
            self._stem_pack_paths = resolved
            if not self._stem_mode or not self._stem_buffers or crossfade_seconds <= 0:
                self._stem_mode = True
                self._stem_buffers = loaded
                self._stem_positions = {
                    lid: self._edge_guard(len(buf)) for lid, buf in loaded.items()
                }
                self._stem_target_buffers = {}
                self._stem_target_positions = {}
                self._stem_pack_fade_remaining = 0
                for lid in loaded:
                    self._stem_gains.setdefault(lid, 0.5)
                    self._stem_gain_targets.setdefault(lid, self._stem_gains[lid])
                # Use a synthetic profile key so discrete path does not fight stems.
                self._profile_id = "__stem__"
                self._target_profile_id = "__stem__"
                return
            self._stem_target_buffers = loaded
            self._stem_target_positions = {
                lid: self._edge_guard(len(buf)) for lid, buf in loaded.items()
            }
            self._stem_pack_fade_total = max(int(crossfade_seconds * self.sample_rate), 1)
            self._stem_pack_fade_remaining = self._stem_pack_fade_total
            for lid in loaded:
                self._stem_gains.setdefault(lid, 0.0)
                self._stem_gain_targets.setdefault(lid, 0.5)

    def set_layer_gains(
        self,
        gains: dict[str, float],
        slew_seconds: float = 1.0,
    ) -> None:
        with self._lock:
            if not self._stem_mode:
                return
            targets = {k: max(0.0, min(1.0, float(v))) for k, v in gains.items()}
            # Zero gains for layers no longer listed.
            for lid in list(self._stem_gains.keys()):
                if lid not in targets:
                    targets[lid] = 0.0
            self._stem_gain_targets = targets
            for lid in targets:
                self._stem_gains.setdefault(lid, 0.0)
            if slew_seconds <= 0:
                self._stem_gains = dict(targets)
                self._stem_slew_remaining = 0
            else:
                self._stem_slew_total = max(int(slew_seconds * self.sample_rate), 1)
                self._stem_slew_remaining = self._stem_slew_total

    def crossfade_to_track(
        self,
        path: Path,
        duration_seconds: float,
        params: AudioParameters | None = None,
    ) -> None:
        """Crossfade to a concrete audio file (intensity loop / song variant)."""
        if not path.is_file():
            logger.warning("crossfade_to_track: missing file %s", path)
            return
        data = self._load_track(path)
        if data is None:
            logger.warning("crossfade_to_track: failed to decode %s", path)
            return
        key = str(path.resolve())
        with self._lock:
            # Discrete intensity path takes over from stem mixing.
            self._stem_mode = False
            self._stem_pack_fade_remaining = 0
            self._buffers[key] = data
            if key not in self._positions:
                self._positions[key] = self._edge_guard(len(data))
            self._profile_track[key] = path
            current = self._profile_id
            if current not in self._buffers or not self._playing or current == "__stem__":
                self._profile_id = key
                self._target_profile_id = key
                self._crossfade_remaining = 0
                if params is not None:
                    self._params = params
                    self._target_params = params
                return
            if key == current:
                if params is not None:
                    self._params = params
                    self._target_params = params
                return
            self._target_profile_id = key
            self._crossfade_total = max(int(duration_seconds * self.sample_rate), 1)
            self._crossfade_remaining = self._crossfade_total
            if params is not None:
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

    def _read_stem_mix(
        self,
        buffers: dict[str, np.ndarray],
        positions: dict[str, int],
        gains: dict[str, float],
        frames: int,
    ) -> tuple[np.ndarray, dict[str, int]]:
        out = np.zeros(frames, dtype=np.float32)
        new_pos = dict(positions)
        for layer_id, buf in buffers.items():
            if buf is None or len(buf) == 0:
                continue
            length = len(buf)
            pos = int(new_pos.get(layer_id, 0)) % length
            # Always advance playheads — even when muted — so layers that share
            # a common source stay phase-locked. Otherwise a layer that unmutes
            # later restarts from the loop head and overlaps mid-phrase content
            # still audible in harmony/pad.
            end = pos + frames
            if end <= length:
                chunk = buf[pos:end]
                new_pos[layer_id] = end % length
            else:
                first = length - pos
                chunk = np.concatenate((buf[pos:], buf[: frames - first]))
                new_pos[layer_id] = (frames - first) % length
            g = float(gains.get(layer_id, 0.0))
            if g > 1e-6:
                out += chunk.astype(np.float32, copy=False) * g
        return np.clip(out, -1.0, 1.0), new_pos

    def _advance_stem_gains(self, frames: int) -> dict[str, float]:
        with self._lock:
            gains = dict(self._stem_gains)
            targets = dict(self._stem_gain_targets)
            rem = self._stem_slew_remaining
            total = self._stem_slew_total
        if rem <= 0:
            with self._lock:
                self._stem_gains = dict(targets)
            return targets
        t = 1.0 - (rem / max(total, 1))
        blended = {}
        for lid in set(gains) | set(targets):
            a = gains.get(lid, 0.0)
            b = targets.get(lid, 0.0)
            blended[lid] = a + (b - a) * t
        rem -= frames
        with self._lock:
            self._stem_gains = blended
            if rem <= 0:
                self._stem_gains = dict(targets)
                self._stem_slew_remaining = 0
                return targets
            self._stem_slew_remaining = rem
        return blended

    def _render(self, frames: int) -> np.ndarray:
        with self._lock:
            stem_mode = self._stem_mode
            params = self._params
            target_params = self._target_params
            pack_fade_rem = self._stem_pack_fade_remaining
            pack_fade_total = self._stem_pack_fade_total
            stem_buffers = dict(self._stem_buffers)
            stem_positions = dict(self._stem_positions)
            stem_target_buffers = dict(self._stem_target_buffers)
            stem_target_positions = dict(self._stem_target_positions)
            profile = self._profile_id
            target = self._target_profile_id
            fade_rem = self._crossfade_remaining
            fade_total = self._crossfade_total

        if stem_mode and stem_buffers:
            gains = self._advance_stem_gains(frames)
            current, new_pos = self._read_stem_mix(
                stem_buffers, stem_positions, gains, frames
            )
            with self._lock:
                if self._stem_buffers is not None:
                    self._stem_positions = new_pos
            current = self._apply_params(current, params)

            if pack_fade_rem > 0 and stem_target_buffers:
                t = 1.0 - (pack_fade_rem / max(pack_fade_total, 1))
                gain_a, gain_b = self._equal_power_weights(t)
                target_block, t_pos = self._read_stem_mix(
                    stem_target_buffers, stem_target_positions, gains, frames
                )
                target_block = self._apply_params(target_block, target_params)
                mixed = current * gain_a + target_block * gain_b
                pack_fade_rem -= frames
                with self._lock:
                    self._stem_target_positions = t_pos
                    if pack_fade_rem <= 0:
                        self._stem_buffers = self._stem_target_buffers
                        self._stem_positions = t_pos
                        self._stem_target_buffers = {}
                        self._stem_target_positions = {}
                        self._stem_pack_fade_remaining = 0
                        self._params = target_params
                    else:
                        self._stem_pack_fade_remaining = pack_fade_rem
                out = mixed
            else:
                out = current
            result = (out * self.master_volume).astype(np.float32)
            self._update_visualiser(result)
            return result

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

        result = (out * self.master_volume).astype(np.float32)
        self._update_visualiser(result)
        return result

    def _update_visualiser(self, result: np.ndarray) -> None:
        """Store RMS + 48-band magnitudes for the Home EQ ring."""
        self._current_level = float(np.sqrt(np.mean(result**2)) + 1e-8)
        try:
            self._current_bands = _band_magnitudes(
                result, self._band_edges, self.sample_rate
            )
        except Exception:
            self._current_bands = [0.0] * self._n_bands


# ---------------------------------------------------------------------------
# FFT frequency‑band helpers (module‑level so they compile once)
# ---------------------------------------------------------------------------

def _build_band_edges(
    n_bands: int, sr: int, low_hz: float = 40.0
) -> np.ndarray:
    """Log‑spaced band edges from *low_hz* to Nyquist."""
    high_hz = sr / 2.0
    return np.logspace(np.log10(low_hz), np.log10(high_hz), n_bands + 1)


def _band_magnitudes(
    block: np.ndarray, edges: np.ndarray, sr: int
) -> list[float]:
    """Return *len(edges)-1* normalised (0‑1) magnitudes for an audio block."""
    # Mono‑compatible — use first channel if stereo
    mono = block if block.ndim == 1 else block[:, 0]
    n = len(mono)
    spec = np.abs(np.fft.rfft(mono)) / n
    freqs = np.fft.rfftfreq(n, 1.0 / sr)

    bands: list[float] = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (freqs >= lo) & (freqs < hi)
        if mask.any():
            bands.append(float(np.mean(spec[mask])))
        else:
            bands.append(0.0)

    # Normalise to 0‑1 (clamp, avoid division by zero)
    mx = max(bands)
    if mx > 1e-8:
        bands = [min(1.0, v / mx) for v in bands]
    return bands

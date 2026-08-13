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


def muffle_cutoff_hz(muffling: float) -> float:
    """Map muffling amount to LPF cutoff.

    0–1 is the normal focus curve (~8 kHz → ~180 Hz). Values in (1, 2]
    reuse the (m-1) curve then divide cutoff by 10 (Pomodoro break).
    """
    m = max(0.0, float(muffling))
    inner = min(1.0, m if m <= 1.0 else m - 1.0)
    cutoff = 8000.0 * (1.0 - inner) + 180.0 * inner
    if m > 1.0:
        cutoff = cutoff / 10.0
    return max(40.0, cutoff)


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
        self._params = AudioParameters(0.5, 0.4, 0.55, 0.0)
        self._target_params = self._params
        self._crossfade_remaining = 0
        self._crossfade_total = 1
        self._stream = None
        self._buffers: dict[str, np.ndarray] = {}
        self._positions: dict[str, int] = {}
        self._profile_track: dict[str, Path] = {}
        self._track_cache: dict[str, np.ndarray] = {}
        self._muffle_z = 0.0
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
        # Frozen outgoing gains while a new pack equal-power fades in.
        self._stem_pack_from_gains: dict[str, float] = {}
        self._loop_xf = max(32, int(sample_rate * 0.008))
        # Phrase-boundary switch state (wait → fadeout → gap → new track).
        self._switch_phase = "idle"  # idle | wait | fadeout | gap
        self._switch_wait_remaining = 0
        self._switch_fade_total = 1
        self._switch_fade_remaining = 0
        self._switch_gap_remaining = 0
        self._switch_target_key: str | None = None
        self._switch_target_params: AudioParameters | None = None
        # Phrase-boundary switch for stem packs (wait → fadeout → gap → new pack).
        self._stem_switch_phase = "idle"  # idle | wait | fadeout | gap
        self._stem_switch_wait_remaining = 0
        self._stem_switch_fade_total = 1
        self._stem_switch_fade_remaining = 0
        self._stem_switch_gap_remaining = 0
        self._stem_switch_layers: dict[str, np.ndarray] = {}
        self._stem_switch_resolved: dict[str, Path] = {}
        # New-song entrance ramp after a phrase switch (slightly weaker start).
        self._switch_fade_in_total = 1
        self._switch_fade_in_remaining = 0
        self._stem_switch_fade_in_total = 1
        self._stem_switch_fade_in_remaining = 0
        # Live EQ / level for HomePage ring.
        self._current_level: float = 0.0
        self._n_bands = 48
        self._band_edges: np.ndarray = _build_band_edges(
            self._n_bands, sample_rate, 40.0
        )
        self._current_bands: list[float] = [0.0] * self._n_bands
        self._chime: np.ndarray | None = None
        self._chime_pos = 0


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
            self._stem_pack_from_gains = {}
            self._stem_mode = False
            self._reset_phrase_switch()

    def _reset_phrase_switch(self) -> None:
        """Cancel any pending phrase-boundary switch (caller holds the lock)."""
        self._switch_phase = "idle"
        self._switch_wait_remaining = 0
        self._switch_fade_remaining = 0
        self._switch_gap_remaining = 0
        self._switch_target_key = None
        self._switch_target_params = None
        self._stem_switch_phase = "idle"
        self._stem_switch_wait_remaining = 0
        self._stem_switch_fade_remaining = 0
        self._stem_switch_gap_remaining = 0
        self._stem_switch_layers = {}
        self._stem_switch_resolved = {}
        self._switch_fade_in_remaining = 0
        self._stem_switch_fade_in_remaining = 0

    def _edge_guard(self, length: int) -> int:
        """Start after the loop splice head so the first sample is near-silent."""
        if length <= 1:
            return 0
        xf = min(self._loop_xf, length // 8)
        return xf if length > 2 * xf else 0

    def _splice_loop(self, data: np.ndarray) -> np.ndarray:
        """Equal-power splice the tail into the head so wrap-around is click-free."""
        n = int(len(data))
        xf = min(self._loop_xf, n // 8)
        if n < 2 * xf + 8 or xf < 8:
            return data
        out = data.copy()
        t = np.linspace(0.0, 1.0, xf, dtype=np.float32)
        fade_out = np.cos(t * np.pi * 0.5).astype(np.float32)
        fade_in = np.sin(t * np.pi * 0.5).astype(np.float32)
        out[-xf:] = out[-xf:] * fade_out + out[:xf] * fade_in
        return out

    def _advance_loop_pos(self, pos: int, frames: int, length: int) -> int:
        """Advance a playhead, skipping the spliced head after a wrap."""
        if length <= 0:
            return 0
        xf = min(self._loop_xf, length // 8) if length > 2 * self._loop_xf else 0
        nxt = pos + frames
        if nxt < length:
            return nxt
        wrapped = nxt - length
        if xf and wrapped < xf:
            return xf + wrapped
        return wrapped % length

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
        scaled = self._splice_loop(scaled)
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
        with self._lock:
            self._reset_phrase_switch()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def set_profile(self, profile_id: str) -> None:
        self._assign_random_track(profile_id, force_new=True)
        with self._lock:
            self._reset_phrase_switch()
            self._profile_id = profile_id
            self._target_profile_id = profile_id

    def set_parameters(self, params: AudioParameters) -> None:
        """Keep outgoing params frozen while a crossfade / pack fade is active."""
        with self._lock:
            fading = (
                self._crossfade_remaining > 0
                or self._stem_pack_fade_remaining > 0
                or self._stem_switch_phase in {"wait", "fadeout", "gap"}
                or self._switch_phase in {"wait", "fadeout", "gap"}
            )
            self._target_params = params
            if not fading:
                self._params = params

    def set_master_volume(self, volume: float) -> None:
        self.master_volume = max(0.0, min(1.0, float(volume)))

    def play_notification(self, kind: str) -> None:
        """Queue a one-shot chime mixed on top of the current output (not muffled)."""
        from adaptive_soundscape.audio.chimes import render_chime

        samples = render_chime(kind, self.sample_rate)
        with self._lock:
            self._chime = samples
            self._chime_pos = 0

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
            self._reset_phrase_switch()
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
                self._stem_pack_from_gains = {}
                for lid in loaded:
                    self._stem_gains.setdefault(lid, 0.5)
                    self._stem_gain_targets.setdefault(lid, self._stem_gains[lid])
                # Use a synthetic profile key so discrete path does not fight stems.
                self._profile_id = "__stem__"
                self._target_profile_id = "__stem__"
                return
            self._stem_pack_from_gains = dict(self._stem_gains)
            self._stem_target_buffers = loaded
            self._stem_target_positions = {
                lid: self._edge_guard(len(buf)) for lid, buf in loaded.items()
            }
            self._stem_pack_fade_total = max(int(crossfade_seconds * self.sample_rate), 1)
            self._stem_pack_fade_remaining = self._stem_pack_fade_total
            # Incoming pack starts silent; director slews targets via set_layer_gains.
            incoming = {lid: 0.0 for lid in loaded}
            self._stem_gains = dict(incoming)
            self._stem_gain_targets = dict(incoming)

    def fade_out_and_switch_stems(
        self,
        layers: dict[str, Path],
        *,
        wait_seconds: float,
        fadeout_seconds: float = 3.0,
        gap_seconds: float = 0.5,
        fadein_seconds: float = 2.0,
    ) -> None:
        """Wait until the current phrase ends, fade the stem pack out, then swap.

        Mirrors ``fade_out_and_switch`` but targets the layered stem pack: the
        current mix keeps playing untouched during ``wait_seconds``, fades to
        silence over ``fadeout_seconds``, holds a short gap, then the decoded
        new pack takes over, entering at a slightly reduced level and ramping
        up over ``fadein_seconds`` before slewing to the gains configured
        afterwards by ``set_layer_gains``.
        """
        loaded: dict[str, np.ndarray] = {}
        resolved: dict[str, Path] = {}
        for layer_id, path in layers.items():
            if not path.is_file():
                logger.warning(
                    "fade_out_and_switch_stems: missing %s → %s", layer_id, path
                )
                continue
            data = self._load_track(path)
            if data is None:
                logger.warning(
                    "fade_out_and_switch_stems: decode failed %s", path
                )
                continue
            loaded[layer_id] = data
            resolved[layer_id] = path.resolve()
        if not loaded:
            logger.warning("fade_out_and_switch_stems: no layers loaded")
            return
        with self._lock:
            self._reset_phrase_switch()
            if not self._stem_mode or not self._stem_buffers:
                # No pack playing yet — take over immediately.
                self._stem_mode = True
                self._stem_buffers = loaded
                self._stem_positions = {
                    lid: self._edge_guard(len(buf)) for lid, buf in loaded.items()
                }
                self._stem_pack_paths = resolved
                for lid in loaded:
                    self._stem_gains.setdefault(lid, 0.5)
                    self._stem_gain_targets.setdefault(lid, self._stem_gains[lid])
                self._profile_id = "__stem__"
                self._target_profile_id = "__stem__"
                return
            if self._stem_pack_paths == resolved:
                # Same pack already playing — keep playheads, just re-arm gains.
                for lid in loaded:
                    self._stem_gains.setdefault(lid, 0.0)
                    self._stem_gain_targets.setdefault(lid, self._stem_gains[lid])
                return
            # Cancel any in-progress pack crossfade so we own the fade.
            self._stem_target_buffers = {}
            self._stem_target_positions = {}
            self._stem_pack_fade_remaining = 0
            self._stem_switch_phase = "wait"
            self._stem_switch_wait_remaining = max(
                int(wait_seconds * self.sample_rate), 1
            )
            self._stem_switch_fade_total = max(
                int(fadeout_seconds * self.sample_rate), 1
            )
            self._stem_switch_fade_remaining = self._stem_switch_fade_total
            self._stem_switch_gap_remaining = max(
                int(gap_seconds * self.sample_rate), 1
            )
            self._stem_switch_layers = loaded
            self._stem_switch_resolved = resolved
            self._stem_switch_fade_in_remaining = 0
            self._stem_switch_fade_in_total = max(
                int(fadein_seconds * self.sample_rate), 1
            )

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
            self._reset_phrase_switch()
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

    def playback_position(self) -> float | None:
        """Loop-relative playhead of the current track, in seconds.

        Works for both discrete tracks and layered stem packs (all layers are
        phase-locked, so any layer's playhead is representative). Returns
        ``None`` when nothing is playing.
        """
        with self._lock:
            if not self._playing:
                return None
            if self._stem_mode:
                if not self._stem_positions:
                    return None
                lid = next(iter(self._stem_positions))
                pos = self._stem_positions[lid]
                buf = self._stem_buffers.get(lid)
            else:
                key = self._profile_id
                pos = self._positions.get(key, 0)
                buf = self._buffers.get(key)
        if buf is None or len(buf) == 0:
            return None
        return pos / float(self.sample_rate)

    def fade_out_and_switch(
        self,
        path: Path,
        *,
        wait_seconds: float,
        fadeout_seconds: float = 3.0,
        gap_seconds: float = 0.5,
        params: AudioParameters | None = None,
        fadein_seconds: float = 2.0,
    ) -> None:
        """Keep playing the current track for *wait_seconds*, then fade it out
        over *fadeout_seconds*, hold *gap_seconds* of silence, and start
        *path* fresh from its loop head.

        All timing is driven inside the audio callback — this method never
        blocks the audio thread with sleeps.  The new track enters at a
        slightly reduced level and ramps up over ``fadein_seconds``.
        """
        if not path.is_file():
            logger.warning("fade_out_and_switch: missing file %s", path)
            return
        data = self._load_track(path)
        if data is None:
            logger.warning("fade_out_and_switch: failed to decode %s", path)
            return
        key = str(path.resolve())
        with self._lock:
            # Discrete path takes over from stem mixing.
            self._stem_mode = False
            self._stem_pack_fade_remaining = 0
            self._buffers[key] = data
            if key not in self._positions:
                self._positions[key] = self._edge_guard(len(data))
            self._profile_track[key] = path
            current = self._profile_id
            if (
                current not in self._buffers
                or not self._playing
                or current == "__stem__"
                or key == current
            ):
                # Nothing meaningful playing — switch immediately.
                self._profile_id = key
                self._target_profile_id = key
                self._crossfade_remaining = 0
                self._reset_phrase_switch()
                if params is not None:
                    self._params = params
                    self._target_params = params
                return
            self._switch_target_key = key
            self._switch_target_params = params
            self._switch_wait_remaining = max(
                int(round(wait_seconds * self.sample_rate)), 0
            )
            self._switch_fade_total = max(
                int(round(fadeout_seconds * self.sample_rate)), 1
            )
            self._switch_fade_remaining = self._switch_fade_total
            self._switch_gap_remaining = max(
                int(round(gap_seconds * self.sample_rate)), 0
            )
            self._switch_phase = "wait"
            self._target_profile_id = key
            self._crossfade_remaining = 0
            self._switch_fade_in_remaining = 0
            self._switch_fade_in_total = max(
                int(round(fadein_seconds * self.sample_rate)), 1
            )

    def _complete_phrase_switch(
        self, key: str | None, params: AudioParameters | None
    ) -> None:
        """Start the pending track.  Caller must hold the mixer lock."""
        if key is not None and key in self._buffers:
            self._profile_id = key
        self._target_profile_id = self._profile_id
        self._crossfade_remaining = 0
        if params is not None:
            self._params = params
            self._target_params = params
        self._reset_phrase_switch()
        # The new track enters slightly weaker and ramps up to full level.
        self._switch_fade_in_remaining = self._switch_fade_in_total

    def _render_phrase_switch(self, current: np.ndarray, frames: int) -> np.ndarray:
        """Advance the wait → fadeout → gap → next-track state machine."""
        with self._lock:
            phase = self._switch_phase
            wait_rem = self._switch_wait_remaining
            fade_rem = self._switch_fade_remaining
            fade_total = self._switch_fade_total
            gap_rem = self._switch_gap_remaining
            key = self._switch_target_key
            target_params = self._switch_target_params
        if phase == "wait":
            wait_rem -= frames
            with self._lock:
                if wait_rem <= 0:
                    self._switch_phase = "fadeout"
                    self._switch_wait_remaining = 0
                else:
                    self._switch_wait_remaining = wait_rem
            return current
        if phase == "fadeout":
            t = 1.0 - (fade_rem / max(fade_total, 1))
            gain = self._fade_out_gain(t)  # pronounced fade-out for the old song
            out = current * gain
            fade_rem -= frames
            with self._lock:
                if fade_rem <= 0:
                    self._switch_phase = "gap"
                    self._switch_fade_remaining = 0
                else:
                    self._switch_fade_remaining = fade_rem
            return out
        if phase == "gap":
            gap_rem -= frames
            with self._lock:
                if gap_rem <= 0:
                    self._complete_phrase_switch(key, target_params)
                else:
                    self._switch_gap_remaining = gap_rem
            return np.zeros(frames, dtype=np.float32)
        return current

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
        out = np.empty(frames, dtype=np.float32)
        xf = min(self._loop_xf, length // 8) if length > 2 * self._loop_xf else 0
        wrap_to = xf
        p = pos % length
        for i in range(frames):
            out[i] = buffer[p]
            p += 1
            if p >= length:
                p = wrap_to
        with self._lock:
            if self._buffers.get(profile_id) is buffer:
                self._positions[profile_id] = p
        return out

    def _apply_params(self, block: np.ndarray, params: AudioParameters) -> np.ndarray:
        brightness = 0.5 + (params.brightness - 0.5) * 0.4
        energy = 0.5 + (params.energy - 0.5) * 0.5
        warmth = params.warmth
        shaped = block * energy
        shaped = shaped * (0.85 + brightness * 0.3)
        shaped = shaped * (0.9 + warmth * 0.15)
        muffling = max(0.0, float(getattr(params, "muffling", 0.0)))
        if muffling > 1e-4:
            shaped = self._apply_muffle_lpf(shaped, muffling)
        else:
            self._muffle_z = float(shaped[-1]) if len(shaped) else self._muffle_z
        return np.clip(shaped, -1.0, 1.0)

    def _apply_muffle_lpf(self, block: np.ndarray, muffling: float) -> np.ndarray:
        """Stateful one-pole low-pass.

        0–1: cutoff ~8 kHz → ~180 Hz (focus muffling).
        1–2: the (m-1) curve is applied then divided by 10 (Pomodoro break).
        """
        cutoff = muffle_cutoff_hz(muffling)
        # One-pole coefficient: alpha ≈ 1 - exp(-2π fc / fs)
        alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff / float(self.sample_rate))
        alpha = max(1e-4, min(1.0, alpha))
        out = np.empty_like(block, dtype=np.float32)
        z = float(self._muffle_z)
        for i, sample in enumerate(block):
            z = z + alpha * (float(sample) - z)
            out[i] = z
        self._muffle_z = z
        return out

    @staticmethod
    def _equal_power_weights(t: float) -> tuple[float, float]:
        """Return (current_gain, target_gain) for equal-power crossfade."""
        t = max(0.0, min(1.0, t))
        return math.cos(t * math.pi * 0.5), math.sin(t * math.pi * 0.5)

    @staticmethod
    def _fade_out_gain(t: float) -> float:
        """Pronounced fade-out curve (quadratic) — the old song clearly ducks."""
        t = max(0.0, min(1.0, t))
        return (1.0 - t) ** 2

    @staticmethod
    def _fade_in_gain(t: float) -> float:
        """Cosine fade-in from silence — never a 70% step that clicks."""
        t = max(0.0, min(1.0, t))
        return math.sin(t * math.pi * 0.5)

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
            xf = min(self._loop_xf, length // 8) if length > 2 * self._loop_xf else 0
            wrap_to = xf
            # Always advance playheads — even when muted — so layers that share
            # a common source stay phase-locked.
            end = pos + frames
            if end <= length:
                chunk = buf[pos:end]
                new_pos[layer_id] = end
            else:
                first = length - pos
                rest = frames - first
                head = buf[wrap_to : wrap_to + rest] if rest else buf[:0]
                if len(head) < rest:
                    # Extremely short buffer — fall back to modular wrap.
                    chunk = np.concatenate((buf[pos:], buf[:rest]))
                    new_pos[layer_id] = rest % length
                else:
                    chunk = np.concatenate((buf[pos:], head))
                    new_pos[layer_id] = wrap_to + rest
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

    def _advance_stem_switch(
        self, current: np.ndarray, frames: int
    ) -> np.ndarray:
        """Advance the stem phrase-switch state machine (called from _render)."""
        with self._lock:
            phase = self._stem_switch_phase
            wait_rem = self._stem_switch_wait_remaining
            fade_rem = self._stem_switch_fade_remaining
            fade_total = self._stem_switch_fade_total
            gap_rem = self._stem_switch_gap_remaining
        if phase == "wait":
            wait_rem -= frames
            with self._lock:
                self._stem_switch_wait_remaining = max(wait_rem, 0)
                if wait_rem <= 0:
                    self._stem_switch_phase = "fadeout"
            return current
        if phase == "fadeout":
            t = 1.0 - (fade_rem / max(fade_total, 1))
            gain = self._fade_out_gain(t)  # pronounced fade-out for the old pack
            fade_rem -= frames
            with self._lock:
                self._stem_switch_fade_remaining = max(fade_rem, 0)
                if fade_rem <= 0:
                    self._stem_switch_phase = "gap"
            return current * gain
        if phase == "gap":
            gap_rem -= frames
            if gap_rem <= 0:
                self._complete_stem_switch()
            else:
                with self._lock:
                    self._stem_switch_gap_remaining = gap_rem
            return np.zeros(frames, dtype=np.float32)
        return current

    def _complete_stem_switch(self) -> None:
        """Swap in the decoded new pack once the fade-out + gap finished."""
        with self._lock:
            loaded = self._stem_switch_layers
            resolved = self._stem_switch_resolved
            if loaded:
                self._stem_buffers = loaded
                self._stem_positions = {
                    lid: self._edge_guard(len(buf)) for lid, buf in loaded.items()
                }
                self._stem_pack_paths = resolved
                for lid in loaded:
                    # Enter from silence so the fade-in cosine has no step.
                    self._stem_gains[lid] = 0.0
                    self._stem_gain_targets.setdefault(lid, 0.5)
                self._stem_mode = True
                self._profile_id = "__stem__"
                self._target_profile_id = "__stem__"
            self._stem_switch_phase = "idle"
            self._stem_switch_wait_remaining = 0
            self._stem_switch_fade_remaining = 0
            self._stem_switch_gap_remaining = 0
            self._stem_switch_layers = {}
            self._stem_switch_resolved = {}
            # The new pack enters slightly weaker and ramps up to full level.
            self._stem_switch_fade_in_remaining = self._stem_switch_fade_in_total

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
            switch_phase = self._switch_phase

        if stem_mode and stem_buffers:
            with self._lock:
                stem_switch_phase = self._stem_switch_phase
                from_gains = dict(self._stem_pack_from_gains)
            if stem_switch_phase == "idle":
                gains = self._advance_stem_gains(frames)
            else:
                # Freeze per-layer gains while a phrase switch is in progress,
                # so the current pack keeps its level until the fade-out starts.
                gains = dict(self._stem_gains)
            outgoing_gains = from_gains or gains
            current, new_pos = self._read_stem_mix(
                stem_buffers, stem_positions, outgoing_gains, frames
            )
            with self._lock:
                if self._stem_buffers is not None:
                    self._stem_positions = new_pos

            with self._lock:
                stem_switch_phase = self._stem_switch_phase
            if stem_switch_phase != "idle":
                current = self._apply_params(current, params)
                out = self._advance_stem_switch(current, frames)
            elif pack_fade_rem > 0 and stem_target_buffers:
                t = 1.0 - (pack_fade_rem / max(pack_fade_total, 1))
                gain_a, gain_b = self._equal_power_weights(t)
                target_block, t_pos = self._read_stem_mix(
                    stem_target_buffers, stem_target_positions, gains, frames
                )
                mixed = current * gain_a + target_block * gain_b
                shaped = self._apply_params(mixed, params.lerp(target_params, t))
                pack_fade_rem -= frames
                with self._lock:
                    self._stem_target_positions = t_pos
                    if pack_fade_rem <= 0:
                        self._stem_buffers = self._stem_target_buffers
                        self._stem_positions = t_pos
                        self._stem_target_buffers = {}
                        self._stem_target_positions = {}
                        self._stem_pack_fade_remaining = 0
                        self._stem_pack_from_gains = {}
                        self._params = target_params
                    else:
                        self._stem_pack_fade_remaining = pack_fade_rem
                out = shaped
            else:
                out = self._apply_params(current, params)
            # New pack enters slightly weaker after a phrase switch.
            with self._lock:
                sfin_rem = self._stem_switch_fade_in_remaining
                sfin_total = self._stem_switch_fade_in_total
            if sfin_rem > 0:
                t = 1.0 - (sfin_rem / max(sfin_total, 1))
                out = out * self._fade_in_gain(t)
                sfin_rem = max(sfin_rem - frames, 0)
                with self._lock:
                    self._stem_switch_fade_in_remaining = sfin_rem
            result = (out * self.master_volume).astype(np.float32)
            self._update_visualiser(result)
            return self._overlay_chime(result, frames)

        current = self._read_loop(profile, frames)
        if switch_phase != "idle":
            current = self._apply_params(current, params)
            out = self._render_phrase_switch(current, frames)
        elif fade_rem > 0 and target != profile:
            t = 1.0 - (fade_rem / max(fade_total, 1))
            gain_a, gain_b = self._equal_power_weights(t)
            target_block = self._read_loop(target, frames)
            mixed = current * gain_a + target_block * gain_b
            out = self._apply_params(mixed, params.lerp(target_params, t))
            fade_rem -= frames
            if fade_rem <= 0:
                with self._lock:
                    self._profile_id = target
                    self._params = target_params
                    self._crossfade_remaining = 0
            else:
                with self._lock:
                    self._crossfade_remaining = fade_rem
        else:
            out = self._apply_params(current, params)

        # New track enters slightly weaker after a phrase switch.
        with self._lock:
            fin_rem = self._switch_fade_in_remaining
            fin_total = self._switch_fade_in_total
        if fin_rem > 0:
            t = 1.0 - (fin_rem / max(fin_total, 1))
            out = out * self._fade_in_gain(t)
            fin_rem = max(fin_rem - frames, 0)
            with self._lock:
                self._switch_fade_in_remaining = fin_rem

        result = (out * self.master_volume).astype(np.float32)
        self._update_visualiser(result)
        return self._overlay_chime(result, frames)

    def _overlay_chime(self, result: np.ndarray, frames: int) -> np.ndarray:
        """Mix a queued notification chime on top (clear of the music LPF)."""
        with self._lock:
            chime = self._chime
            pos = self._chime_pos
        if chime is None or pos >= len(chime):
            return result
        take = min(frames, len(chime) - pos)
        mixed = result.copy()
        mixed[:take] = np.clip(mixed[:take] + chime[pos : pos + take], -1.0, 1.0)
        pos += take
        with self._lock:
            if pos >= len(chime):
                self._chime = None
                self._chime_pos = 0
            else:
                self._chime_pos = pos
        return mixed

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

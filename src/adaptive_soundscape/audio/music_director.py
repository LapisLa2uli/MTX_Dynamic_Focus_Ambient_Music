"""Authoritative adaptive music director (layered stems + discrete fallback)."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from adaptive_soundscape.audio.album import is_debug_song, list_songs, pick_random_song
from adaptive_soundscape.audio.layer_mix import (
    LAYER_IDS,
    LayerMixConfig,
    compute_layer_gains,
    curves_from_mapping,
)
from adaptive_soundscape.audio.music_manifest import (
    MusicIntensity,
    TrackEntry,
    list_playable_tracks,
    load_manifest,
    nearest_available_intensity,
)
from adaptive_soundscape.audio.parameters import AudioParameters
from adaptive_soundscape.audio.phrase_boundary import PhraseBoundaryDetector

logger = logging.getLogger(__name__)


class TrackAudioBackend(Protocol):
    """Minimal backend surface used by MusicDirector."""

    def start(self, profile_id: str | None = None) -> None: ...

    def stop(self) -> None: ...

    def set_parameters(self, params: AudioParameters) -> None: ...

    def crossfade_to_track(
        self,
        path: Path,
        duration_seconds: float,
        params: AudioParameters | None = None,
    ) -> None: ...

    def playback_position(self) -> float | None: ...

    def fade_out_and_switch(
        self,
        path: Path,
        *,
        wait_seconds: float,
        fadeout_seconds: float = 3.0,
        gap_seconds: float = 0.5,
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

    @property
    def is_playing(self) -> bool: ...

    def set_master_volume(self, volume: float) -> None: ...


@dataclass
class AdaptiveMusicConfig:
    enabled: bool = True
    intensity_smoothing: float = 0.35
    enter_focus: float = 0.40
    enter_deep_focus: float = 0.70
    leave_deep_focus: float = 0.60
    leave_focus: float = 0.30
    min_state_seconds: float = 3.0
    recovery_seconds: float = 8.0
    default_crossfade_ms: int = 1500
    master_volume: float = 0.75
    gain_slew_seconds: float = 1.0
    energy_limit: float = 2.4
    recovery_peak: float = 0.55
    layer_mix: dict[str, list[list[float]]] = field(default_factory=dict)
    phrase_boundary_enabled: bool = True
    phrase_boundary_threshold: float = 0.40
    phrase_search_seconds: float = 10.0
    phrase_fadeout_seconds: float = 3.0
    phrase_gap_seconds: float = 0.5
    fallback_crossfade_seconds: float = 4.0
    scenario_crossfade_seconds: float = 4.0


class MusicDirector:
    """Map focus_score → layer gains (default) or discrete intensity loops (fallback)."""

    def __init__(
        self,
        assets_dir: Path,
        backend: TrackAudioBackend,
        config: AdaptiveMusicConfig | None = None,
        *,
        rng: random.Random | None = None,
    ) -> None:
        self.assets_dir = assets_dir
        self.backend = backend
        self.config = config or AdaptiveMusicConfig()
        self._rng = rng or random.Random()
        self._layer_mix = LayerMixConfig(
            curves=curves_from_mapping(self.config.layer_mix),
            gain_slew_seconds=self.config.gain_slew_seconds,
            energy_limit=self.config.energy_limit,
            recovery_peak=self.config.recovery_peak,
            recovery_seconds=self.config.recovery_seconds,
        )
        self._smoothed = 0.5
        self._scenario = "unknown"
        self._song_dir: Path | None = None
        self._playback_mode = "discrete"
        self._layer_paths: dict[str, Path] = {}
        self._layer_gains: dict[str, float] = {}
        self._active_state = MusicIntensity.FOCUS
        self._requested_state = MusicIntensity.FOCUS
        self._request_since = time.monotonic()
        self._state_since = time.monotonic()
        self._active_track_id: str | None = None
        self._active_path: Path | None = None
        self._last_track_by_state: dict[MusicIntensity, str] = {}
        self._recovery_until = 0.0
        self._was_deep = False
        self._enabled = False
        self._muted = False
        self._debug_layer_override = False
        self._include_debug_songs = False
        self._debug_layer_gains: dict[str, float] = {
            lid: 0.7 for lid in LAYER_IDS
        }
        self._volume = self.config.master_volume
        self._params = AudioParameters(0.5, 0.4, 0.55)
        self._boundary = PhraseBoundaryDetector(
            assets_dir,
            threshold=self.config.phrase_boundary_threshold,
            search_seconds=self.config.phrase_search_seconds,
        )

    # --- public status ---
    @property
    def active_state(self) -> MusicIntensity:
        return self._active_state

    @property
    def active_song_id(self) -> str | None:
        return self._song_dir.name if self._song_dir else None

    @property
    def active_track_id(self) -> str | None:
        return self._active_track_id

    @property
    def playback_mode(self) -> str:
        return self._playback_mode

    @property
    def layer_gains(self) -> dict[str, float]:
        return dict(self._layer_gains)

    @property
    def is_playing(self) -> bool:
        return self._enabled and self.backend.is_playing and not self._muted

    @property
    def smoothed_intensity(self) -> float:
        return self._smoothed

    # --- controls ---
    def play(self) -> None:
        self._enabled = True
        if not self.backend.is_playing:
            try:
                self.backend.start(profile_id=self._scenario)
            except Exception:
                logger.exception("MusicDirector: backend start failed")
                self._enabled = False
                return
        self._apply_volume()
        self._ensure_playing_current()

    def pause(self) -> None:
        self._enabled = False
        try:
            self.backend.stop()
        except Exception:
            logger.exception("MusicDirector: backend stop failed")

    def shutdown(self) -> None:
        self.pause()
        self._song_dir = None
        self._active_path = None
        self._active_track_id = None
        self._layer_paths.clear()
        self._layer_gains.clear()

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        self._apply_volume()

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self._apply_volume()

    def set_parameters(self, params: AudioParameters) -> None:
        self._params = params
        try:
            self.backend.set_parameters(params)
        except Exception:
            logger.exception("MusicDirector: set_parameters failed")

    # --- scenario / intensity ---
    def set_scenario(self, profile_id: str, focus_score: float | None = None) -> None:
        same_profile = profile_id == self._scenario and self._song_dir is not None
        self._scenario = profile_id
        if same_profile:
            # Keep the active song/stems; only refresh intensity / gains.
            if focus_score is not None:
                self._smoothed = max(0.0, min(1.0, focus_score))
            self._resolve_playback_mode()
            if self._enabled:
                if self._playback_mode == "layered":
                    # Reload only if layer files changed; otherwise just re-apply gains.
                    self._load_layered(force=False)
                else:
                    self._ensure_playing_current()
            return

        exclude = self._song_dir
        song = pick_random_song(
            self.assets_dir,
            profile_id,
            exclude=exclude,
            rng=self._rng,
            include_debug=self._include_debug_songs,
        )
        self._song_dir = song
        self._last_track_by_state.clear()
        # Keep _active_path: it still points at the currently playing file, so
        # the (non-force) transition below can wait for a phrase boundary in
        # the current track before fading to the new one.
        self._active_track_id = None
        self._recovery_until = 0.0
        self._was_deep = False
        if focus_score is not None:
            self._smoothed = max(0.0, min(1.0, focus_score))
        desired = self._map_score_to_state(self._smoothed, self._active_state)
        self._active_state = desired
        self._requested_state = desired
        self._state_since = time.monotonic()
        self._request_since = self._state_since
        self._resolve_playback_mode()
        if self._enabled:
            if self._playback_mode == "layered":
                self._load_layered(force=False, phrase_switch=True)
            else:
                self._transition_to(desired, force=False)

    def album_song_ids(self, profile_id: str | None = None) -> list[str]:
        pid = profile_id or self._scenario or "unknown"
        return [
            p.name
            for p in list_songs(
                self.assets_dir, pid, include_debug=self._include_debug_songs
            )
        ]

    def set_include_debug_songs(self, enabled: bool) -> None:
        """Allow ui_debug_* mixes in rotation only while Settings debug is on."""
        was = self._include_debug_songs
        self._include_debug_songs = bool(enabled)
        if was and not self._include_debug_songs:
            if self._song_dir is not None and is_debug_song(self._song_dir):
                # Drop the debug family so set_scenario cannot keep it.
                self._song_dir = None
                self.set_scenario(self._scenario, self._smoothed)

    def set_song(self, song_id: str, *, focus_score: float | None = None) -> None:
        """Crossfade to a named song in the current scenario album."""
        pid = self._scenario or "unknown"
        target = self.assets_dir / pid / song_id
        if not target.is_dir():
            logger.warning("MusicDirector: song not found %s/%s", pid, song_id)
            return
        if not self._include_debug_songs and is_debug_song(target):
            logger.info("MusicDirector: skipping debug song %s (debug mode off)", song_id)
            return
        if self._song_dir is not None and target.resolve() == self._song_dir.resolve():
            return
        self._song_dir = target
        self._last_track_by_state.clear()
        self._active_track_id = None
        self._recovery_until = 0.0
        if focus_score is not None:
            self._smoothed = max(0.0, min(1.0, focus_score))
        desired = self._map_score_to_state(self._smoothed, self._active_state)
        self._active_state = desired
        self._requested_state = desired
        self._state_since = time.monotonic()
        self._request_since = self._state_since
        self._resolve_playback_mode()
        if self._enabled:
            if self._playback_mode == "layered":
                self._load_layered(force=False, phrase_switch=True)
            else:
                self._transition_to(desired, force=False)

    def force_intensity(self, focus_score: float) -> None:
        """Snap smoothed intensity (used by debug concentration override)."""
        self._smoothed = max(0.0, min(1.0, float(focus_score)))
        if self._playback_mode == "layered":
            self._apply_layered_gains()

    def update_intensity(self, focus_score: float) -> None:
        if not self.config.enabled:
            return
        score = max(0.0, min(1.0, focus_score))
        alpha = max(0.0, min(0.99, self.config.intensity_smoothing))
        self._smoothed = alpha * self._smoothed + (1.0 - alpha) * score

        now = time.monotonic()
        # UI / discrete state label (also used for recovery event in layered mode).
        label_state = self._map_score_to_state(self._smoothed, self._active_state)

        if self._playback_mode == "layered":
            leaving_deep = (
                self._active_state == MusicIntensity.DEEP_FOCUS
                and label_state != MusicIntensity.DEEP_FOCUS
            )
            if leaving_deep:
                self._was_deep = True
                if "recovery" in self._layer_paths:
                    self._recovery_until = now + self._layer_mix.recovery_seconds
            if label_state == MusicIntensity.DEEP_FOCUS:
                self._was_deep = True
                if self._smoothed >= self.config.enter_deep_focus:
                    self._recovery_until = 0.0
            if self._active_state != label_state:
                held = now - self._state_since
                if held >= self.config.min_state_seconds or label_state == MusicIntensity.DEEP_FOCUS:
                    self._active_state = label_state
                    self._state_since = now
            self._apply_layered_gains()
            return

        # --- discrete intensity file switching ---
        if now < self._recovery_until and self._active_state == MusicIntensity.RECOVERY:
            if self._smoothed >= self.config.enter_deep_focus:
                self._recovery_until = 0.0
            else:
                return

        desired = label_state
        if (
            self._active_state == MusicIntensity.DEEP_FOCUS
            and desired != MusicIntensity.DEEP_FOCUS
            and self._was_deep
        ):
            if self._song_has_intensity(MusicIntensity.RECOVERY):
                desired = MusicIntensity.RECOVERY

        if desired != self._requested_state:
            self._requested_state = desired
            self._request_since = now

        if desired == self._active_state:
            if (
                self._active_state == MusicIntensity.RECOVERY
                and now >= self._recovery_until
            ):
                nxt = self._map_score_to_state(self._smoothed, MusicIntensity.FOCUS)
                if nxt == MusicIntensity.DEEP_FOCUS:
                    nxt = MusicIntensity.FOCUS
                self._requested_state = nxt
                self._request_since = now
            return

        held = now - self._state_since
        requested_for = now - self._request_since
        if held < self.config.min_state_seconds or requested_for < self.config.min_state_seconds:
            return

        self._transition_to(desired, force=False)

    # --- internals ---
    def _resolve_playback_mode(self) -> None:
        self._layer_paths = {}
        self._playback_mode = "discrete"
        if self._song_dir is None:
            return
        manifest = load_manifest(self._song_dir)
        if manifest is None:
            return
        if manifest.prefers_layered(self._song_dir):
            self._playback_mode = "layered"
            self._layer_paths = manifest.playable_layer_paths(self._song_dir)

    def _load_layered(self, *, force: bool, phrase_switch: bool = False) -> None:
        if not self._layer_paths:
            self._resolve_playback_mode()
        if not self._layer_paths:
            self._playback_mode = "discrete"
            self._transition_to(self._active_state, force=True)
            return
        crossfade_s = max(0.5, float(self.config.scenario_crossfade_seconds))
        if self._song_dir is not None:
            manifest = load_manifest(self._song_dir)
            if manifest is not None:
                crossfade_s = max(
                    crossfade_s, max(manifest.crossfade_ms, 50) / 1000.0
                )
        if force:
            crossfade_s = min(crossfade_s, 0.35)

        # Phrase-boundary switch: keep the current pack playing until the
        # active state's phrase ends, then fade out + gap + load the new pack.
        used_phrase = False
        if (
            phrase_switch
            and not force
            and self.config.phrase_boundary_enabled
            and self._active_path is not None
            and self._active_path.is_file()
        ):
            pos_getter = getattr(self.backend, "playback_position", None)
            switch_fn = getattr(self.backend, "fade_out_and_switch_stems", None)
            if callable(pos_getter) and callable(switch_fn):
                try:
                    pos_sec = pos_getter()
                    if pos_sec is not None:
                        boundary = self._boundary.search_boundary(
                            self._active_path, pos_sec
                        )
                        if boundary is not None:
                            wait_seconds = max(0.0, boundary - pos_sec)
                            switch_fn(
                                self._layer_paths,
                                wait_seconds=wait_seconds,
                                fadeout_seconds=self.config.phrase_fadeout_seconds,
                                gap_seconds=self.config.phrase_gap_seconds,
                            )
                            used_phrase = True
                except Exception:
                    logger.exception(
                        "MusicDirector: stem phrase-boundary switch failed"
                    )
        if self._enabled and not used_phrase:
            # No sentence end within the look-ahead budget (10 s / 50
            # detections): fall back to a 3 s crossfade, never an abrupt swap.
            if (
                phrase_switch
                and not force
                and self.config.phrase_boundary_enabled
            ):
                crossfade_s = max(
                    crossfade_s, self.config.scenario_crossfade_seconds
                )
            try:
                self.backend.load_stem_pack(self._layer_paths, crossfade_s)
            except Exception:
                logger.exception("MusicDirector: load_stem_pack failed")
                self._playback_mode = "discrete"
                self._transition_to(self._active_state, force=True)
                return
        self._apply_layered_gains()
        self._active_track_id = "+".join(sorted(self._layer_paths.keys()))
        self._active_path = self._current_state_full_track()

    def _current_state_full_track(self) -> Path | None:
        """Single-file rendering of the active intensity, used as the phrase
        analysis source while a layered pack is playing."""
        if self._song_dir is None:
            return None
        playable = list_playable_tracks(self._song_dir, self._active_state)
        if not playable:
            return None
        return playable[0][1]

    def set_debug_layer_override(
        self, enabled: bool, gains: dict[str, float] | None = None
    ) -> None:
        """When enabled, use manual per-layer gains instead of focus curves."""
        self._debug_layer_override = bool(enabled)
        if gains:
            for key, value in gains.items():
                self._debug_layer_gains[str(key)] = max(0.0, min(1.0, float(value)))
        if self._playback_mode == "layered":
            self._apply_layered_gains()

    def set_debug_layer_gain(self, layer_id: str, gain: float) -> None:
        self._debug_layer_gains[str(layer_id)] = max(0.0, min(1.0, float(gain)))
        if self._debug_layer_override and self._playback_mode == "layered":
            self._apply_layered_gains()

    def _apply_layered_gains(self) -> None:
        if self._debug_layer_override:
            available = set(self._layer_paths.keys())
            gains = {
                lid: self._debug_layer_gains.get(lid, 0.0)
                for lid in LAYER_IDS
                if lid in available
            }
            self._layer_gains = gains
            if not self._enabled:
                return
            try:
                self.backend.set_layer_gains(gains, min(0.35, self._layer_mix.gain_slew_seconds))
            except Exception:
                logger.exception("MusicDirector: set_layer_gains (debug) failed")
            return

        recovery_active = (
            time.monotonic() < self._recovery_until and "recovery" in self._layer_paths
        )
        gains = compute_layer_gains(
            self._smoothed,
            available=set(self._layer_paths.keys()),
            config=self._layer_mix,
            recovery_active=recovery_active,
        )
        self._layer_gains = gains
        if not self._enabled:
            return
        try:
            self.backend.set_layer_gains(gains, self._layer_mix.gain_slew_seconds)
        except Exception:
            logger.exception("MusicDirector: set_layer_gains failed")

    def _map_score_to_state(
        self, score: float, current: MusicIntensity
    ) -> MusicIntensity:
        cfg = self.config
        if current == MusicIntensity.DEEP_FOCUS:
            if score <= cfg.leave_deep_focus:
                return MusicIntensity.FOCUS if score >= cfg.leave_focus else MusicIntensity.CALM
            return MusicIntensity.DEEP_FOCUS
        if current == MusicIntensity.FOCUS:
            if score >= cfg.enter_deep_focus:
                return MusicIntensity.DEEP_FOCUS
            if score <= cfg.leave_focus:
                return MusicIntensity.CALM
            return MusicIntensity.FOCUS
        if current == MusicIntensity.RECOVERY:
            if score >= cfg.enter_deep_focus:
                return MusicIntensity.DEEP_FOCUS
            if score >= cfg.enter_focus:
                return MusicIntensity.FOCUS
            return MusicIntensity.CALM
        if score >= cfg.enter_deep_focus:
            return MusicIntensity.DEEP_FOCUS
        if score >= cfg.enter_focus:
            return MusicIntensity.FOCUS
        return MusicIntensity.CALM

    def _song_has_intensity(self, intensity: MusicIntensity) -> bool:
        if self._song_dir is None:
            return False
        return bool(list_playable_tracks(self._song_dir, intensity))

    def _pick_variation(
        self, intensity: MusicIntensity
    ) -> tuple[TrackEntry, Path] | None:
        if self._song_dir is None:
            return None
        available = nearest_available_intensity(self._song_dir, intensity)
        if available is None:
            logger.warning(
                "MusicDirector: no playable tracks in song %s", self._song_dir
            )
            return None
        if available != intensity:
            logger.warning(
                "MusicDirector: missing %s, falling back to %s in %s",
                intensity.value,
                available.value,
                self._song_dir.name,
            )
            intensity = available
        playable = list_playable_tracks(self._song_dir, intensity)
        if not playable:
            return None
        last_id = self._last_track_by_state.get(intensity)
        candidates = playable
        if last_id and len(playable) > 1:
            filtered = [(e, p) for e, p in playable if e.id != last_id]
            if filtered:
                candidates = filtered
        return self._rng.choice(candidates)

    def _transition_to(self, desired: MusicIntensity, *, force: bool) -> None:
        picked = self._pick_variation(desired)
        if picked is None:
            return
        entry, path = picked
        effective = desired
        if self._song_dir is not None:
            nearest = nearest_available_intensity(self._song_dir, desired)
            if nearest is not None:
                effective = nearest

        leaving_deep = self._active_state == MusicIntensity.DEEP_FOCUS
        if leaving_deep:
            self._was_deep = True

        # --- phrase-boundary switching (real status changes only) ---
        used_phrase = False
        phrase_capable = (
            self._enabled
            and not force
            and self.config.phrase_boundary_enabled
            and self._active_path is not None
            and self._active_path.is_file()
        )
        pos_getter = getattr(self.backend, "playback_position", None)
        switch_fn = getattr(self.backend, "fade_out_and_switch", None)
        if phrase_capable and callable(pos_getter) and callable(switch_fn):
            try:
                pos_sec = pos_getter()
                if pos_sec is not None:
                    boundary = self._boundary.search_boundary(self._active_path, pos_sec)
                    if boundary is not None:
                        wait_seconds = max(0.0, boundary - pos_sec)
                        logger.info(
                            "MusicDirector: phrase boundary at %.2fs → "
                            "fadeout %.1fs + gap %.1fs, then %s",
                            boundary,
                            self.config.phrase_fadeout_seconds,
                            self.config.phrase_gap_seconds,
                            path.name,
                        )
                        switch_fn(
                            path,
                            wait_seconds=wait_seconds,
                            fadeout_seconds=self.config.phrase_fadeout_seconds,
                            gap_seconds=self.config.phrase_gap_seconds,
                            params=self._params,
                        )
                        used_phrase = True
                    else:
                        logger.info(
                            "MusicDirector: no phrase boundary within %.0fs → "
                            "%.0fs crossfade",
                            self.config.phrase_search_seconds,
                            self.config.scenario_crossfade_seconds,
                        )
            except Exception:
                logger.exception("MusicDirector: phrase boundary detection failed")

        if self._enabled and not used_phrase:
            if phrase_capable:
                crossfade_s = max(self.config.scenario_crossfade_seconds, 0.5)
            else:
                crossfade_s = max(self.config.scenario_crossfade_seconds, 0.5)
            try:
                self.backend.crossfade_to_track(
                    path, crossfade_s if not force else min(crossfade_s, 0.35), self._params
                )
            except Exception:
                logger.exception("MusicDirector: crossfade_to_track failed for %s", path)
                return

        self._active_state = effective
        self._requested_state = effective
        self._active_track_id = entry.id
        self._active_path = path
        self._last_track_by_state[effective] = entry.id
        now = time.monotonic()
        self._state_since = now
        self._request_since = now

        if effective == MusicIntensity.DEEP_FOCUS:
            self._was_deep = True
            self._recovery_until = 0.0
        elif effective == MusicIntensity.RECOVERY:
            self._recovery_until = now + self.config.recovery_seconds
        elif leaving_deep and effective != MusicIntensity.RECOVERY:
            self._was_deep = False

    def _ensure_playing_current(self) -> None:
        self._resolve_playback_mode()
        if self._playback_mode == "layered":
            self._load_layered(force=True)
            return
        if self._active_path is not None and self._active_path.is_file():
            try:
                self.backend.crossfade_to_track(self._active_path, 0.25, self._params)
                return
            except Exception:
                logger.exception("MusicDirector: resume current track failed")
        self._transition_to(self._active_state, force=True)

    def _apply_volume(self) -> None:
        vol = 0.0 if self._muted else self._volume
        setter = getattr(self.backend, "set_master_volume", None)
        if callable(setter):
            try:
                setter(vol)
                return
            except Exception:
                logger.exception("MusicDirector: set_master_volume failed")
        if hasattr(self.backend, "master_volume"):
            try:
                setattr(self.backend, "master_volume", vol)
            except Exception:
                pass


def config_from_settings(adaptive: Any) -> AdaptiveMusicConfig:
    layer_mix = getattr(adaptive, "layer_mix", {}) or {}
    if not isinstance(layer_mix, dict):
        layer_mix = {}
    return AdaptiveMusicConfig(
        enabled=bool(getattr(adaptive, "enabled", True)),
        intensity_smoothing=float(getattr(adaptive, "intensity_smoothing", 0.35)),
        enter_focus=float(getattr(adaptive, "enter_focus", 0.40)),
        enter_deep_focus=float(getattr(adaptive, "enter_deep_focus", 0.70)),
        leave_deep_focus=float(getattr(adaptive, "leave_deep_focus", 0.60)),
        leave_focus=float(getattr(adaptive, "leave_focus", 0.30)),
        min_state_seconds=float(getattr(adaptive, "min_state_seconds", 3.0)),
        recovery_seconds=float(getattr(adaptive, "recovery_seconds", 8.0)),
        default_crossfade_ms=int(getattr(adaptive, "default_crossfade_ms", 1500)),
        master_volume=float(getattr(adaptive, "master_volume", 0.75)),
        gain_slew_seconds=float(getattr(adaptive, "gain_slew_seconds", 1.0)),
        energy_limit=float(getattr(adaptive, "energy_limit", 2.4)),
        recovery_peak=float(getattr(adaptive, "recovery_peak", 0.55)),
        layer_mix=layer_mix,
        phrase_boundary_enabled=bool(
            getattr(adaptive, "phrase_boundary_enabled", True)
        ),
        phrase_boundary_threshold=float(
            getattr(adaptive, "phrase_boundary_threshold", 0.40)
        ),
        phrase_search_seconds=float(
            getattr(adaptive, "phrase_search_seconds", 10.0)
        ),
        phrase_fadeout_seconds=float(
            getattr(adaptive, "phrase_fadeout_seconds", 3.0)
        ),
        phrase_gap_seconds=float(getattr(adaptive, "phrase_gap_seconds", 0.5)),
        fallback_crossfade_seconds=float(
            getattr(adaptive, "fallback_crossfade_seconds", 4.0)
        ),
        scenario_crossfade_seconds=float(
            getattr(adaptive, "scenario_crossfade_seconds", 4.0)
        ),
    )

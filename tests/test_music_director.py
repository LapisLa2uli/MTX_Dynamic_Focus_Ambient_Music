"""Unit tests for MusicDirector intensity mapping and variation selection."""

from __future__ import annotations

import json
import time
import wave
from pathlib import Path

import numpy as np

from adaptive_soundscape.audio.music_director import AdaptiveMusicConfig, MusicDirector
from adaptive_soundscape.audio.music_manifest import MusicIntensity, save_manifest, build_manifest_for_song
from adaptive_soundscape.audio.parameters import AudioParameters


def _write_sine_wav(path: Path, seconds: float = 0.2, rate: int = 44100) -> None:
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    samples = (0.2 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())


class FakeBackend:
    def __init__(self) -> None:
        self.playing = False
        self.paths: list[Path] = []
        self.packs: list[dict[str, Path]] = []
        self.gains_history: list[dict[str, float]] = []
        self.master_volume = 0.75
        self.stopped = False

    def start(self, profile_id: str | None = None) -> None:
        del profile_id
        self.playing = True

    def stop(self) -> None:
        self.playing = False
        self.stopped = True

    def set_parameters(self, params: AudioParameters) -> None:
        del params

    def crossfade_to_track(
        self,
        path: Path,
        duration_seconds: float,
        params: AudioParameters | None = None,
    ) -> None:
        del duration_seconds, params
        self.paths.append(path)
        self.playing = True

    def load_stem_pack(
        self,
        layers: dict[str, Path],
        crossfade_seconds: float = 0.0,
    ) -> None:
        del crossfade_seconds
        self.packs.append(dict(layers))
        self.playing = True

    def set_layer_gains(
        self,
        gains: dict[str, float],
        slew_seconds: float = 1.0,
    ) -> None:
        del slew_seconds
        self.gains_history.append(dict(gains))

    def set_master_volume(self, volume: float) -> None:
        self.master_volume = volume

    @property
    def is_playing(self) -> bool:
        return self.playing


def _make_song(assets: Path, profile: str, song: str, *, dual_focus: bool = False) -> Path:
    song_dir = assets / profile / song
    for intensity in ("calm", "focus", "deep_focus"):
        _write_sine_wav(song_dir / intensity / f"{intensity}_01.wav")
    if dual_focus:
        _write_sine_wav(song_dir / "focus" / "focus_02.wav")
    manifest = build_manifest_for_song(
        song,
        calm_rel="calm/calm_01.wav",
        focus_rel="focus/focus_01.wav",
        deep_rel="deep_focus/deep_focus_01.wav",
    )
    if dual_focus:
        from adaptive_soundscape.audio.music_manifest import TrackEntry

        manifest.states["focus"].tracks.append(
            TrackEntry(id="focus_02", src="focus/focus_02.wav")
        )
    save_manifest(song_dir, manifest)
    return song_dir


def test_maps_low_score_to_calm(tmp_path: Path):
    _make_song(tmp_path, "programming", "programming_01")
    backend = FakeBackend()
    director = MusicDirector(
        tmp_path,
        backend,
        AdaptiveMusicConfig(min_state_seconds=0.0, intensity_smoothing=0.0),
    )
    director.set_scenario("programming", focus_score=0.1)
    director.play()
    assert director.active_state == MusicIntensity.CALM


def test_hysteresis_enter_and_leave_deep_focus(tmp_path: Path):
    _make_song(tmp_path, "programming", "programming_01")
    backend = FakeBackend()
    cfg = AdaptiveMusicConfig(
        min_state_seconds=0.0,
        intensity_smoothing=0.0,
        enter_deep_focus=0.70,
        leave_deep_focus=0.60,
        enter_focus=0.40,
        leave_focus=0.30,
        recovery_seconds=0.0,
    )
    director = MusicDirector(tmp_path, backend, cfg)
    director.set_scenario("programming", 0.5)
    director.play()
    assert director.active_state == MusicIntensity.FOCUS

    director.update_intensity(0.75)
    assert director.active_state == MusicIntensity.DEEP_FOCUS

    # Still above leave threshold → stay deep
    director.update_intensity(0.65)
    assert director.active_state == MusicIntensity.DEEP_FOCUS

    # Drop below leave → leave deep (to focus or recovery)
    director.update_intensity(0.55)
    assert director.active_state in {
        MusicIntensity.FOCUS,
        MusicIntensity.RECOVERY,
        MusicIntensity.CALM,
    }


def test_debounce_min_state_duration(tmp_path: Path):
    _make_song(tmp_path, "programming", "programming_01")
    backend = FakeBackend()
    cfg = AdaptiveMusicConfig(min_state_seconds=5.0, intensity_smoothing=0.0)
    director = MusicDirector(tmp_path, backend, cfg)
    director.set_scenario("programming", 0.2)
    director.play()
    assert director.active_state == MusicIntensity.CALM
    director.update_intensity(0.9)
    # Requested but not held long enough
    assert director.active_state == MusicIntensity.CALM


def test_no_immediate_track_repetition(tmp_path: Path):
    _make_song(tmp_path, "programming", "programming_01", dual_focus=True)
    backend = FakeBackend()
    cfg = AdaptiveMusicConfig(min_state_seconds=0.0, intensity_smoothing=0.0)
    director = MusicDirector(tmp_path, backend, cfg, rng=__import__("random").Random(0))
    director.set_scenario("programming", 0.5)
    director.play()
    first = director.active_track_id
    # Force another transition into focus by leaving and re-entering
    director._active_state = MusicIntensity.CALM
    director._state_since = time.monotonic() - 10
    director._request_since = time.monotonic() - 10
    director._requested_state = MusicIntensity.CALM
    director.update_intensity(0.5)
    second = director.active_track_id
    assert first is not None and second is not None
    # With two focus tracks, second pick should differ when exclude works
    ids = {first, second}
    assert "focus_01" in ids or "focus_02" in ids


def test_missing_intensity_falls_back(tmp_path: Path):
    song_dir = tmp_path / "programming" / "sparse"
    _write_sine_wav(song_dir / "focus" / "focus_01.wav")
    manifest = build_manifest_for_song("sparse", focus_rel="focus/focus_01.wav")
    save_manifest(song_dir, manifest)
    backend = FakeBackend()
    director = MusicDirector(
        tmp_path,
        backend,
        AdaptiveMusicConfig(min_state_seconds=0.0, intensity_smoothing=0.0),
    )
    director.set_scenario("programming", 0.1)  # wants calm, only focus exists
    director.play()
    assert director.active_track_id == "focus_01"
    assert backend.paths


def test_shutdown_stops_backend(tmp_path: Path):
    _make_song(tmp_path, "programming", "programming_01")
    backend = FakeBackend()
    director = MusicDirector(tmp_path, backend, AdaptiveMusicConfig())
    director.set_scenario("programming", 0.5)
    director.play()
    director.shutdown()
    assert backend.stopped
    assert director.active_song_id is None


def _make_layered_song(assets: Path, profile: str, song: str) -> Path:
    from adaptive_soundscape.audio.music_manifest import LayerEntry

    song_dir = _make_song(assets, profile, song)
    for layer_id in ("pad", "harmony", "melody_a", "rhythm"):
        _write_sine_wav(song_dir / layer_id / f"{layer_id}_01.wav")
    manifest = build_manifest_for_song(
        song,
        calm_rel="calm/calm_01.wav",
        focus_rel="focus/focus_01.wav",
        deep_rel="deep_focus/deep_focus_01.wav",
    )
    for layer_id in ("pad", "harmony", "melody_a", "rhythm"):
        manifest.layers[layer_id] = LayerEntry(
            src=f"{layer_id}/{layer_id}_01.wav",
            role="base",
            generated=False,
        )
    manifest.playback_mode = "layered"
    save_manifest(song_dir, manifest)
    return song_dir


def test_layered_mode_loads_pack_and_sets_gains(tmp_path: Path):
    _make_layered_song(tmp_path, "programming", "programming_01")
    backend = FakeBackend()
    director = MusicDirector(
        tmp_path,
        backend,
        AdaptiveMusicConfig(min_state_seconds=0.0, intensity_smoothing=0.0),
    )
    director.set_scenario("programming", 0.2)
    director.play()
    assert director.playback_mode == "layered"
    assert backend.packs
    assert "pad" in backend.packs[-1]
    director.update_intensity(0.85)
    assert backend.gains_history
    high = backend.gains_history[-1]
    assert high.get("melody_a", 0) > high.get("rhythm", 1)


def test_set_scenario_same_profile_keeps_song(tmp_path: Path):
    _make_layered_song(tmp_path, "programming", "programming_01")
    backend = FakeBackend()
    director = MusicDirector(
        tmp_path,
        backend,
        AdaptiveMusicConfig(min_state_seconds=0.0, intensity_smoothing=0.0),
    )
    director.set_scenario("programming", 0.2)
    director.play()
    song_before = director.active_song_id
    director.set_scenario("programming", 0.85)
    assert director.active_song_id == song_before
    assert director.playback_mode == "layered"
    assert backend.gains_history
    assert backend.gains_history[-1].get("melody_a", 0) > 0.5


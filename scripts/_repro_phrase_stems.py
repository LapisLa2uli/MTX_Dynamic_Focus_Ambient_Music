"""Verify: layered (default) songs also switch via phrase-boundary detection.

    detect end of phrase -> keep playing -> 3s fade -> gap -> new song/pack

Covers two layers:
  A. scheduler: set_scenario() on layered songs must call fade_out_and_switch_stems
               (not load_stem_pack with a short crossfade)
  B. state machine: PlaceholderMixer.fade_out_and_switch_stems actually drives
               wait -> fadeout -> gap -> new pack in _render()

Run: python scripts/_repro_phrase_stems.py
"""

import logging
import sys
from pathlib import Path

SRC = Path(r"c:/Users/DELL/AFMS/src")
sys.path.insert(0, str(SRC))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

import numpy as np  # noqa: E402

from adaptive_soundscape.audio.music_director import (  # noqa: E402
    AdaptiveMusicConfig,
    MusicDirector,
)
from adaptive_soundscape.audio.placeholder_mixer import PlaceholderMixer  # noqa: E402

ASSETS = Path(r"c:/Users/DELL/AFMS/assets/audio")
SR = 8000
BLOCK = 1024


class FakeBackend:
    def __init__(self, mixer):
        self._mixer = mixer
        self.is_playing = False
        self.calls = []

    def start(self, profile_id=None):
        self._mixer._playing = True
        self.is_playing = True

    def stop(self):
        self._mixer._playing = False
        self.is_playing = False

    def set_parameters(self, params):
        pass

    def set_master_volume(self, volume):
        pass

    def crossfade_to_track(self, path, duration_seconds, params=None):
        self.calls.append(("crossfade", Path(path).name, round(duration_seconds, 2)))

    def playback_position(self):
        return self._mixer.playback_position()

    def fade_out_and_switch_stems(self, layers, *, wait_seconds, fadeout_seconds=3.0,
                                  gap_seconds=0.5, params=None):
        self.calls.append(("stem_phrase", sorted(layers.keys()),
                           round(wait_seconds, 2), round(fadeout_seconds, 2)))

    def load_stem_pack(self, layers, crossfade_seconds, params=None):
        self.calls.append(("stem", sorted(layers.keys()), round(crossfade_seconds, 2)))
        # Real app uses the mixer itself as backend; forward so the pack plays.
        self._mixer.load_stem_pack(layers, crossfade_seconds)

    def set_layer_gains(self, gains, slew_seconds):
        self._mixer.set_layer_gains(gains, slew_seconds)


def make_config():
    return AdaptiveMusicConfig(
        enabled=True,
        intensity_smoothing=0.0,
        min_state_seconds=0.0,
        default_crossfade_ms=1500,
        phrase_boundary_enabled=True,
        phrase_boundary_threshold=0.30,
        phrase_search_seconds=10.0,
        phrase_fadeout_seconds=3.0,
        phrase_gap_seconds=0.5,
        fallback_crossfade_seconds=3.0,
    )


def layer_paths(song_dir: Path) -> dict[str, Path]:
    from adaptive_soundscape.audio.music_manifest import load_manifest
    m = load_manifest(song_dir)
    assert m is not None, f"no manifest in {song_dir}"
    return m.playable_layer_paths(song_dir)


def tick(mixer: PlaceholderMixer, secs: float) -> None:
    n = max(int(secs * SR // BLOCK), 1)
    for _ in range(n):
        mixer._render(BLOCK)


def rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.asarray(block, dtype=np.float32) ** 2)) + 1e-8)


def main() -> None:
    prog = ASSETS / "programming" / "programming_01"
    cdesign = ASSETS / "creative_design" / "creative_design_01"

    # ---- A. scheduler behaviour on layered scenario switch ----
    mixer = PlaceholderMixer(ASSETS, sample_rate=SR, block_size=BLOCK)
    backend = FakeBackend(mixer)
    director = MusicDirector(ASSETS, backend, make_config())
    director.play()
    director.set_scenario("programming", 0.5)
    assert director._playback_mode == "layered", director._playback_mode
    assert director._active_path is not None, "layered mode must keep an analysis path"
    print("[A] after boot: mode =", director._playback_mode,
          "| active_path =", director._active_path.name)
    backend.calls.clear()
    tick(mixer, 2.0)  # let playback_position become non-None
    director.set_scenario("creative_design", 0.5)  # status change -> new song
    print("[A] backend calls on scenario change:")
    for c in backend.calls:
        print("   ", c)
    phrase_calls = [c for c in backend.calls if c[0] == "stem_phrase"]
    assert phrase_calls, "layered scenario change must use fade_out_and_switch_stems; got: " + str(backend.calls)
    assert phrase_calls[0][2] >= 0.0 and phrase_calls[0][3] == 3.0
    print("   OK: layered switch waits for phrase boundary, then 3.0s fade")

    # ---- B. state machine progression (synthetic source for determinism) ----
    mixer2 = PlaceholderMixer(ASSETS, sample_rate=SR, block_size=BLOCK)
    mixer2._playing = True
    sr = mixer2.sample_rate
    t = np.arange(int(1.5 * sr)) / sr
    sine = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    mixer2._stem_buffers = {"synth": sine}
    mixer2._stem_positions = {"synth": 0}
    mixer2._stem_gains = {"synth": 1.0}
    mixer2._stem_gain_targets = {"synth": 1.0}
    mixer2._stem_mode = True
    mixer2._stem_pack_paths = {"synth": Path("synth.wav")}
    pack_b = layer_paths(cdesign)

    wait_sec, fade_sec, gap_sec = 2.0, 0.8, 0.3
    mixer2.fade_out_and_switch_stems(
        pack_b, wait_seconds=wait_sec, fadeout_seconds=fade_sec, gap_seconds=gap_sec
    )
    # The director calls set_layer_gains right after scheduling the switch,
    # so the new pack's targets are armed before it takes over.
    # (slew > 0: targets only, do not overwrite the current gains.)
    mixer2.set_layer_gains({lid: 0.5 for lid in pack_b}, 0.5)
    assert mixer2._stem_switch_phase == "wait"

    def drive_until(phase: str, max_secs: float) -> None:
        n = int(max_secs * SR // BLOCK)
        for _ in range(n):
            mixer2._render(BLOCK)
            if mixer2._stem_switch_phase == phase:
                return
        raise AssertionError(f"never reached phase {phase}; now {mixer2._stem_switch_phase}")

    lvl_wait = sum(rms(mixer2._render(BLOCK)) for _ in range(4)) / 4.0
    assert 0.02 < lvl_wait < 0.6, f"wait phase must keep playing (lvl {lvl_wait:.3f})"
    drive_until("fadeout", 3.0)
    lvl_fade = sum(rms(mixer2._render(BLOCK)) for _ in range(4)) / 4.0
    assert lvl_fade < 0.9 * lvl_wait, f"fadeout must reduce level (lvl {lvl_fade:.3f})"
    drive_until("gap", 2.0)
    lvl_gap = rms(mixer2._render(BLOCK))
    assert lvl_gap < 1e-4, f"gap must be silence (lvl {lvl_gap:.4f})"
    drive_until("idle", 2.0)
    assert mixer2._stem_switch_phase == "idle"
    assert set(mixer2._stem_buffers.keys()) == set(pack_b.keys())
    lvl_new = max(rms(mixer2._render(BLOCK)) for _ in range(12))
    assert lvl_new > 1e-4, f"new pack must be audible (lvl {lvl_new:.5f})"
    print("[B] wait -> fadeout -> gap -> new pack: OK")
    print("     levels: wait %.3f -> fade %.3f -> new %.3f" %
          (lvl_wait, lvl_fade, lvl_new))

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()

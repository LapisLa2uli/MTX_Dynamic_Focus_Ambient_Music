"""Repro 3: user status change (set_scenario) must NOT be an instant swap.

Covers both playback modes:
  A. layered  song -> song:  load_stem_pack(crossfade) must use manifest xfade (1.5s), not 0.35s
  B. discrete song -> song:  must route through phrase-boundary / fade_out_and_switch,
                             or at least a fallback crossfade >= 1.5s (never 0.35s)

Run: python scripts/_repro_status_swap.py
"""

import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

SRC = Path(r"c:/Users/DELL/AFMS/src")
sys.path.insert(0, str(SRC))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from adaptive_soundscape.audio.music_director import (  # noqa: E402
    AdaptiveMusicConfig,
    MusicDirector,
)
from adaptive_soundscape.audio.placeholder_mixer import PlaceholderMixer  # noqa: E402

REAL_ASSETS = Path(r"c:/Users/DELL/AFMS/assets/audio")


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

    def fade_out_and_switch(self, path, *, wait_seconds, fadeout_seconds=3.0,
                            gap_seconds=0.5, params=None):
        self.calls.append(("phrase", Path(path).name, round(wait_seconds, 2)))

    def fade_out_and_switch_stems(self, layers, *, wait_seconds,
                                  fadeout_seconds=3.0, gap_seconds=0.5, params=None):
        self.calls.append(("stem_phrase", sorted(layers.keys()),
                           round(wait_seconds, 2), round(fadeout_seconds, 2)))

    def load_stem_pack(self, layers, crossfade_seconds, params=None):
        self.calls.append(("stem", list(layers.keys()), round(crossfade_seconds, 2)))
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


def build_discrete_song(dst: Path, stem_src: Path, tag: str) -> None:
    """Build a discrete song dir referencing copies of real mp3s + features.json."""
    for intensity, src_name in (
        ("calm", "calm_01.mp3"),
        ("focus", "focus_01.mp3"),
        ("deep_focus", "deep_focus_01.mp3"),
    ):
        out = dst / intensity / f"{tag}_{intensity}.mp3"
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stem_src / intensity / src_name, out)
    manifest = {
        "songId": tag,
        "bpm": 70.0,
        "timeSignature": "4/4",
        "barsPerLoop": 8,
        "crossfadeMs": 1500,
        "loopSeconds": 27.428,
        "playbackMode": "discrete",
        "layers": {},
        "states": {
            "calm": {"tracks": [{"id": f"{tag}_calm", "src": f"calm/{tag}_calm.mp3"}]},
            "focus": {"tracks": [{"id": f"{tag}_focus", "src": f"focus/{tag}_focus.mp3"}]},
            "deepFocus": {"tracks": [{"id": f"{tag}_deep", "src": f"deep_focus/{tag}_deep.mp3"}]},
        },
    }
    (dst / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    shutil.copy2(stem_src / "features.json", dst / "features.json")


def main() -> None:
    stem_src = REAL_ASSETS / "programming" / "programming_01"
    tmp = Path(tempfile.mkdtemp(prefix="afms_status_swap_"))
    try:
        tmp_assets = tmp / "assets"
        build_discrete_song(
            tmp_assets / "profile_a" / "song_a", stem_src, "song_a"
        )
        build_discrete_song(
            tmp_assets / "profile_b" / "song_b", stem_src, "song_b"
        )
        print("tmp assets:", tmp_assets)
        for p in sorted(tmp_assets.rglob("*")):
            if p.is_file():
                print("  ", p.relative_to(tmp_assets))

        def tick(mixer_: PlaceholderMixer, secs: float) -> None:
            n = int(secs * mixer_.sample_rate // mixer_.block_size)
            for _ in range(max(n, 1)):
                mixer_._render(mixer_.block_size)

        # ---------- A. layered scenario switch ----------
        mixer = PlaceholderMixer(REAL_ASSETS, sample_rate=8000, block_size=1024)
        backend = FakeBackend(mixer)
        director = MusicDirector(REAL_ASSETS, backend, make_config())
        director.play()
        director.set_scenario("programming", 0.5)
        backend.calls.clear()
        tick(mixer, 2.0)
        director.set_scenario("creative_design", 0.5)
        print("\n[A] layered programming -> creative_design, backend calls:")
        for call in backend.calls:
            print("   ", call)
        phrase_calls = [c for c in backend.calls if c[0] == "stem_phrase"]
        assert phrase_calls, f"expected fade_out_and_switch_stems; got {backend.calls}"
        assert phrase_calls[0][3] == 3.0, "phrase fadeout must be 3.0s"
        print("   OK: layered switch waits", phrase_calls[0][2],
              "s for phrase end, then 3.0s fade")

        # ---------- B. discrete scenario switch ----------
        mixer2 = PlaceholderMixer(tmp_assets, sample_rate=8000, block_size=1024)
        backend2 = FakeBackend(mixer2)
        director2 = MusicDirector(tmp_assets, backend2, make_config())
        director2.play()
        director2.set_scenario("profile_a", 0.5)  # boot: song_a / focus
        backend2.calls.clear()

        tick(mixer2, 2.0)
        print("\n[B] before status change:", director2._song_dir.name,
              "active:", director2._active_state,
              "phase:", mixer2._switch_phase)

        director2.set_scenario("profile_b", 0.85)  # status change -> new song
        print("[B] backend calls after status change:")
        for call in backend2.calls:
            print("   ", call)
        assert backend2.calls, "expected a backend switch call"
        kind, name, dur = backend2.calls[0]
        if kind == "phrase":
            print("   OK: routed through phrase boundary (wait", dur, "s before fade)")
        else:
            assert dur >= 1.5, (
                f"status change used {dur}s crossfade; expected phrase wait or "
                f">=1.5s crossfade, got an instant swap"
            )
            print("   OK: routed through", dur, "s crossfade (no instant swap)")

        print("\nALL CHECKS PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()

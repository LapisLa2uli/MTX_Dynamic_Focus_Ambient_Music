"""Repro harness: drives the real MusicDirector + PlaceholderMixer without audio hardware.

Simulates the audio callback by calling mixer._render(n) manually, then steps the
director through scenario/intensity changes and logs exactly what happens over time.
"""

import sys
import time
from pathlib import Path

import numpy as np

SRC = Path(r"c:/Users/DELL/AFMS/src")
sys.path.insert(0, str(SRC))

from adaptive_soundscape.audio.music_director import (  # noqa: E402
    AdaptiveMusicConfig,
    MusicDirector,
    MusicIntensity,
    AudioParameters,
)
from adaptive_soundscape.audio.phrase_boundary import PhraseBoundaryDetector  # noqa: E402
from adaptive_soundscape.audio.placeholder_mixer import PlaceholderMixer  # noqa: E402

ASSETS = Path(r"c:/Users/DELL/AFMS/assets/audio")


class FakeBackend:
    """Minimal TrackAudioBackend wrapping a real PlaceholderMixer."""

    def __init__(self, mixer: PlaceholderMixer):
        self._mixer = mixer
        self.is_playing = False

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
        self._mixer.crossfade_to_track(path, duration_seconds, params)

    def playback_position(self):
        return self._mixer.playback_position()

    def fade_out_and_switch(self, path, *, wait_seconds, fadeout_seconds=3.0,
                            gap_seconds=0.5, params=None):
        self._mixer.fade_out_and_switch(path, wait_seconds=wait_seconds,
                                        fadeout_seconds=fadeout_seconds,
                                        gap_seconds=gap_seconds, params=params)

    def load_stem_pack(self, layers, crossfade_seconds, params=None):
        raise RuntimeError("no stems in repro")


def make_config() -> AdaptiveMusicConfig:
    return AdaptiveMusicConfig(
        enabled=True,
        intensity_smoothing=0.0,          # instant score
        min_state_seconds=0.0,            # no hold delay
        default_crossfade_ms=1500,
        phrase_boundary_enabled=True,
        phrase_boundary_threshold=0.30,
        phrase_search_seconds=10.0,
        phrase_fadeout_seconds=3.0,
        phrase_gap_seconds=0.5,
        fallback_crossfade_seconds=3.0,
    )


def pick_track(song_dir: Path, intensity: MusicIntensity) -> Path:
    d = song_dir / intensity.value
    for f in sorted(d.iterdir()):
        if f.suffix.lower() in (".mp3", ".wav", ".flac", ".ogg", ".m4a"):
            return f
    raise FileNotFoundError(intensity)


def main() -> None:
    song_dir = ASSETS / "programming" / "programming_01"
    mixer = PlaceholderMixer(ASSETS, sample_rate=8000, block_size=1024)
    backend = FakeBackend(mixer)
    director = MusicDirector(ASSETS, backend, make_config())
    director._song_dir = song_dir

    # Set up the boundary detector against the same song.
    det = PhraseBoundaryDetector(ASSETS, threshold=0.30, search_seconds=10.0)

    calm = pick_track(song_dir, MusicIntensity.CALM)
    focus = pick_track(song_dir, MusicIntensity.FOCUS)
    deep = pick_track(song_dir, MusicIntensity.DEEP_FOCUS)

    print("=== 1. phrase boundary search results (wait = boundary - pos) ===")
    for pos in (1.0, 5.0, 15.0, 30.0, 60.0, 120.0):
        b = det.search_boundary(calm, pos)
        print(f"  pos={pos:6.1f}s  boundary={None if b is None else round(b,1)}s  "
              f"wait={None if b is None else round(max(0.0, b-pos),1)}s")

    print("\n=== 2. direct mixer phrase-switch timing ===")
    mixer._playing = True
    mixer.crossfade_to_track(calm, 0.35, AudioParameters(0.5, 0.4, 0.55))
    for _ in range(64):
        mixer._render(1024)  # settle crossfade (0.35s at 8k)
    print(f"  after load: profile={mixer._profile_id}")
    pos0 = mixer.playback_position()
    print(f"  playback_position={round(pos0,2)}s")
    mixer.fade_out_and_switch(focus, wait_seconds=4.0, fadeout_seconds=1.0,
                              gap_seconds=0.5, params=AudioParameters(0.5, 0.4, 0.55))
    t0 = time.monotonic()
    for s in range(0, 9):
        n = int(1.0 * mixer.sample_rate // mixer.block_size)
        for _ in range(n):
            mixer._render(mixer.block_size)
        print(f"  t+{s}s  phase={mixer._switch_phase}  profile={mixer._profile_id}  "
              f"pos={round(mixer.playback_position(),2)}s")

    print("\n=== 3. full director flow ===")
    mixer._playing = False
    director.set_scenario("programming", focus_score=0.5)
    director.play()
    print(f"  after play: mode={director.playback_mode}  active_state={director._active_state}  "
          f"active_path={director._active_path}")
    pos = mixer.playback_position()
    print(f"  mixer playing pos={None if pos is None else round(pos,2)}s profile={mixer._profile_id}")

    # Drive a simulated intensity change -> focus
    for _ in range(int(1.0 * mixer.sample_rate // mixer.block_size)):
        mixer._render(mixer.block_size)
    print(f"  before intensity: active={director._active_state} mixer_profile={mixer._profile_id}")
    director.update_intensity(0.85)  # -> DEEP_FOCUS
    print(f"  after update_intensity(0.85): active={director._active_state}  "
          f"active_path={director._active_path}  mixer_profile={mixer._profile_id}  "
          f"phase={mixer._switch_phase}")
    # Let it play out
    for s in range(0, 16):
        n = int(1.0 * mixer.sample_rate // mixer.block_size)
        for _ in range(n):
            mixer._render(mixer.block_size)
        print(f"  t+{s}s  active={director._active_state}  mixer_profile={mixer._profile_id}  "
              f"phase={mixer._switch_phase}  pos={round(mixer.playback_position(),2)}s")


if __name__ == "__main__":
    main()

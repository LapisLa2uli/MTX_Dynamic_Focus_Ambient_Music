"""Repro 2: faithful app loop — repeated update_intensity ticks with a jittery score.

Logs every director decision (phrase boundary vs crossfade vs force) and the
mixer's actual behavior over time, exactly like the running app would.
"""

import logging
import sys
from pathlib import Path

SRC = Path(r"c:/Users/DELL/AFMS/src")
sys.path.insert(0, str(SRC))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from adaptive_soundscape.audio.music_director import (  # noqa: E402
    AdaptiveMusicConfig,
    MusicDirector,
    AudioParameters,
)
from adaptive_soundscape.audio.placeholder_mixer import PlaceholderMixer  # noqa: E402

ASSETS = Path(r"c:/Users/DELL/AFMS/assets/audio")


class FakeBackend:
    def __init__(self, mixer):
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
        raise RuntimeError("no stems")


def main() -> None:
    song_dir = ASSETS / "programming" / "programming_01"
    mixer = PlaceholderMixer(ASSETS, sample_rate=8000, block_size=1024)
    backend = FakeBackend(mixer)
    cfg = AdaptiveMusicConfig(
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
    director = MusicDirector(ASSETS, backend, cfg)
    director._song_dir = song_dir

    director.play()
    print(f"[boot] mode={director.playback_mode} active={director._active_state} "
          f"mixer={mixer._profile_id} phase={mixer._switch_phase}")

    def tick(secs: float) -> None:
        n = int(secs * mixer.sample_rate // mixer.block_size)
        for _ in range(max(n, 1)):
            mixer._render(mixer.block_size)

    tick(1.0)
    print(f"[t+1] mixer={mixer._profile_id} phase={mixer._switch_phase} "
          f"pos={mixer.playback_position():.2f}")

    scores = [0.45, 0.50, 0.42, 0.55, 0.48, 0.52, 0.60, 0.55, 0.65, 0.72,
              0.68, 0.75, 0.80, 0.78, 0.85, 0.82, 0.88, 0.90, 0.86, 0.92]
    sim = 0.0
    for i, sc in enumerate(scores):
        director.update_intensity(sc)
        st = director._active_state
        print(f"[tick{i:02d}] score={sc:.2f} active={st} mixer={mixer._profile_id} "
              f"phase={mixer._switch_phase} pos={mixer.playback_position():.2f}")
        tick(1.0)
        sim += 1.0
        print(f"        t+{sim:5.1f} mixer={mixer._profile_id} phase={mixer._switch_phase} "
              f"pos={mixer.playback_position():.2f}")


if __name__ == "__main__":
    main()

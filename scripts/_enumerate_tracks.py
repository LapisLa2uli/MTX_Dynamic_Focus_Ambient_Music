"""Temporary: enumerate playable tracks + durations."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from adaptive_soundscape.audio.music_manifest import MusicIntensity, list_playable_tracks, song_dirs
from adaptive_soundscape.core.config import load_settings, resolve_assets_dir

settings = load_settings()
assets = resolve_assets_dir(settings)
total = 0
secs = 0.0
for profile_dir in sorted(p for p in assets.iterdir() if p.is_dir()):
    for song in song_dirs(assets, profile_dir.name):
        seen = set()
        for intensity in MusicIntensity:
            for _e, path in list_playable_tracks(song, intensity):
                if path in seen:
                    continue
                seen.add(path)
                total += 1
                try:
                    import soundfile as sf

                    info = sf.info(str(path))
                    secs += info.frames / info.samplerate
                except Exception:
                    pass
print(f"total playable tracks={total}, cumulative duration={secs:.0f}s ({secs/60:.1f} min)")

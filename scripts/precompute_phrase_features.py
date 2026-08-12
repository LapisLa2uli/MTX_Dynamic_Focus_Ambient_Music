"""Precompute 0.2 s tick volume/pitch features for the default songs.

Stores ``features.json`` inside every song family directory so the
phrase-boundary detector can run without librosa at app runtime.

Run with a Python environment that has librosa + numpy + soundfile + pydantic:

    python scripts\\precompute_phrase_features.py

Optionally pass ``--jobs N`` to control the worker count (default: 4).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from adaptive_soundscape.audio.music_manifest import MusicIntensity, list_playable_tracks, song_dirs
from adaptive_soundscape.audio.phrase_boundary import (
    B0,
    B_PITCH,
    B_VOL,
    FEATURES_FILE,
    SAMPLE_RATE,
    TICK_SECONDS,
    WINDOW_SECONDS,
    _tick_features,
)
from adaptive_soundscape.core.config import load_settings, resolve_assets_dir

logger = logging.getLogger("precompute_phrase_features")


def _compute_one(path_str: str) -> tuple[str, dict | None]:
    """Worker: compute features for one track (picklable, module-level)."""
    path = Path(path_str)
    try:
        return path_str, _tick_features(path)
    except Exception:
        logging.getLogger("precompute_phrase_features").exception(
            "precompute_phrase_features: failed %s", path
        )
        return path_str, None


def _playable_paths(song_dir: Path) -> list[Path]:
    seen: dict[str, Path] = {}
    for intensity in MusicIntensity:
        for _entry, path in list_playable_tracks(song_dir, intensity):
            seen.setdefault(str(path.resolve()), path)
    return sorted(seen.values())


def precompute_profile_song(song_dir: Path, pool: ProcessPoolExecutor | None) -> Path | None:
    """Precompute features for the playable intensity tracks of one song."""
    paths = _playable_paths(song_dir)
    if not paths:
        return None
    if pool is None:
        results = [_compute_one(str(p)) for p in paths]
    else:
        results = list(pool.map(_compute_one, [str(p) for p in paths]))
    tracks: dict[str, dict] = {}
    for path_str, feat in results:
        if feat is None:
            continue
        rel = Path(path_str).resolve().relative_to(song_dir).as_posix()
        tracks[rel] = feat
    if not tracks:
        return None
    data = {
        "tick_seconds": TICK_SECONDS,
        "window_seconds": WINDOW_SECONDS,
        "sample_rate": SAMPLE_RATE,
        "constants": {"b0": B0, "b_vol": B_VOL, "b_pitch": B_PITCH},
        "tracks": tracks,
    }
    out = song_dir / FEATURES_FILE
    tmp = out.with_name(out.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, allow_nan=True)
    tmp.replace(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=4, help="parallel workers")
    args = parser.parse_args()

    settings = load_settings()
    assets = resolve_assets_dir(settings)

    jobs: list[tuple[Path, list[Path]]] = []
    for profile_dir in sorted(p for p in assets.iterdir() if p.is_dir()):
        for song_dir in song_dirs(assets, profile_dir.name):
            paths = _playable_paths(song_dir)
            if paths:
                jobs.append((song_dir, paths))
    total_files = sum(len(paths) for _, paths in jobs)
    print(f"Discovered {len(jobs)} songs / {total_files} playable tracks", flush=True)

    done = skipped = 0
    if args.jobs > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            for song_dir, paths in jobs:
                out = precompute_profile_song(song_dir, pool)
                if out is None:
                    skipped += 1
                else:
                    done += 1
                print(f"{'OK' if out else 'SKIP'}  {song_dir.relative_to(assets)} "
                      f"({len(paths)} tracks)", flush=True)
    else:
        for song_dir, paths in jobs:
            out = precompute_profile_song(song_dir, None)
            if out is None:
                skipped += 1
            else:
                done += 1
            print(f"{'OK' if out else 'SKIP'}  {song_dir.relative_to(assets)} "
                  f"({len(paths)} tracks)", flush=True)

    print(f"\nDone: {done} songs precomputed, {skipped} skipped/failed.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

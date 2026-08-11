"""Batch-separate album song mixes into pad/harmony/melody_a/rhythm via Demucs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from adaptive_soundscape.audio.demucs_client import DemucsClient
from adaptive_soundscape.audio.music_manifest import song_dirs
from adaptive_soundscape.audio.separate_stems import (
    needs_separation,
    repair_melody_harmony_layers,
    separate_and_install_stems,
)
from adaptive_soundscape.core.config import load_settings, resolve_assets_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="", help="Limit to one scenario profile id")
    parser.add_argument("--song", default="", help="Limit to one song folder name")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-separate even if separation_meta.json exists or stems look custom",
    )
    parser.add_argument(
        "--repair-mapping",
        action="store_true",
        help=(
            "Fix melody/harmony swap on already-separated songs without calling Demucs "
            "(moves weak vocals bleed out of melody_a)"
        ),
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    cfg = settings.stem_separation
    if not cfg.enabled:
        print("stem_separation.enabled is false in config")
        return 1

    assets = resolve_assets_dir(settings)
    if not assets.is_dir():
        print(f"Assets dir not found: {assets}")
        return 1

    scenarios: list[str]
    if args.scenario:
        scenarios = [args.scenario]
    else:
        scenarios = sorted(p.name for p in assets.iterdir() if p.is_dir())

    targets: list[Path] = []
    for scenario in scenarios:
        if args.song:
            song_dir = assets / scenario / args.song
            if (song_dir / "manifest.json").is_file():
                targets.append(song_dir)
            elif args.scenario:
                print(f"Song not found: {song_dir}")
                return 1
        else:
            targets.extend(song_dirs(assets, scenario))

    if not targets:
        print("No song families found.")
        return 0

    if args.repair_mapping:
        repaired = 0
        for song_dir in targets:
            label = f"{song_dir.parent.name}/{song_dir.name}"
            try:
                written = repair_melody_harmony_layers(
                    song_dir, force=args.force
                )
            except Exception as exc:
                print(f"FAILED {label}: {exc}")
                return 1
            if written:
                print(f"REPAIR {label} → {[p.name for p in written]}")
                repaired += 1
            else:
                print(f"SKIP  {label} (melody/harmony look fine)")
        print(f"Done. Repaired {repaired}/{len(targets)} song(s).")
        return 0

    client = DemucsClient(cfg.api_base_url, timeout_seconds=cfg.timeout_seconds)
    try:
        health = client.health()
        print(f"API health: {health}")
    except RuntimeError as exc:
        print(exc)
        return 1

    failures = 0
    for song_dir in targets:
        scenario = song_dir.parent.name
        label = f"{scenario}/{song_dir.name}"
        if not needs_separation(song_dir, force=args.force):
            print(f"SKIP  {label} (already separated or custom stems)")
            continue
        print(f"SEPARATE {label} …")
        try:
            written = separate_and_install_stems(
                song_dir,
                client=client,
                model=cfg.model,
                force=args.force,
            )
        except Exception as exc:
            print(f"FAILED {label}: {exc}")
            failures += 1
            continue
        print(f"  wrote {[p.name for p in written]}")

    if failures:
        print(f"Done with {failures} failure(s).")
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

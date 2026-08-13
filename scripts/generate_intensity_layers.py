"""Generate MusicGen intensity layers (texture, melody_b) for song families.

Layers are locked to each song's scenario BPM and existing ``loop_seconds``
so they stay in tempo and in phase with the mix. Debug mixes (``ui_debug*``)
are skipped unless ``--include-debug``.

```powershell
conda activate MTX
python scripts/generate_intensity_layers.py --all --force --layers texture,melody_b
python scripts/generate_intensity_layers.py --scenario programming --song programming_gen_01
```
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
except Exception:
    pass

from adaptive_soundscape.audio.album import is_debug_song
from adaptive_soundscape.audio.generate_layers import generate_and_install_layer
from adaptive_soundscape.audio.music_manifest import song_dirs
from adaptive_soundscape.audio.musicgen_client import MusicGenClient
from adaptive_soundscape.audio.sidecar_lifecycle import SidecarLifecycle
from adaptive_soundscape.core.config import load_settings, resolve_assets_dir


def _layer_installed(song_dir: Path, layer_id: str) -> bool:
    layer_dir = song_dir / layer_id
    if not layer_dir.is_dir():
        return False
    return any(
        p.is_file() and p.suffix.lower() in {".wav", ".mp3"}
        for p in layer_dir.iterdir()
    )


def _stable_seed(name: str, base: int) -> int:
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()
    return int(base) + (int(digest[:8], 16) % 100000)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="", help="Scenario profile id")
    parser.add_argument("--song", default="", help="Song folder name")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate for every song family under assets/audio",
    )
    parser.add_argument(
        "--layers",
        default="",
        help="Comma-separated layer ids (default: config generative_layers.output_layers)",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even when a layer WAV already exists",
    )
    parser.add_argument(
        "--include-debug",
        action="store_true",
        help="Also generate layers for ui_debug_* / debug mixes",
    )
    args = parser.parse_args(argv)

    if not args.all and not (args.scenario and args.song):
        parser.error("Provide --scenario and --song, or use --all")

    settings = load_settings()
    gen = settings.generative_layers
    side_cfg = settings.sidecar_apis
    if not gen.enabled:
        print("generative_layers.enabled is false in config")
        return 1
    assets = resolve_assets_dir(settings)

    layers = [x.strip() for x in args.layers.split(",") if x.strip()]
    if not layers:
        layers = list(gen.output_layers)

    targets: list[Path] = []
    if args.all:
        scenarios = (
            [args.scenario]
            if args.scenario
            else sorted(p.name for p in assets.iterdir() if p.is_dir())
        )
        for scenario in scenarios:
            targets.extend(song_dirs(assets, scenario))
    else:
        song_dir = assets / args.scenario / args.song
        if not (song_dir / "manifest.json").is_file():
            print(f"Song not found: {song_dir}")
            return 1
        targets = [song_dir]

    if not args.include_debug:
        kept: list[Path] = []
        for song_dir in targets:
            if is_debug_song(song_dir):
                print(f"SKIP  {song_dir.parent.name}/{song_dir.name} (debug mix)")
                continue
            kept.append(song_dir)
        targets = kept

    if not targets:
        print("No song families found.")
        return 0

    lifecycle = SidecarLifecycle(
        demucs_env=settings.stem_separation.conda_env,
        musicgen_env=gen.conda_env,
        startup_timeout_seconds=side_cfg.startup_timeout_seconds,
        stop_when_done=side_cfg.stop_when_done,
    )
    try:
        if gen.auto_start_api:
            print("Ensuring MusicGen sidecar…")
            lifecycle.ensure(lifecycle.musicgen)

        client = MusicGenClient(gen.api_base_url, timeout_seconds=gen.timeout_seconds)
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
            if not (song_dir / "manifest.json").is_file():
                print(f"SKIP  {label} (no manifest)")
                continue
            song_seed = _stable_seed(f"{label}:{args.seed}", args.seed)
            for layer_id in layers:
                if not args.force and _layer_installed(song_dir, layer_id):
                    print(f"SKIP  {label}/{layer_id} (already present)")
                    continue
                layer_seed = _stable_seed(f"{label}/{layer_id}", song_seed)
                print(f"GENERATE {label}/{layer_id} (bpm-locked, seed={layer_seed}) …")
                try:
                    dest = generate_and_install_layer(
                        song_dir,
                        scenario=scenario,
                        layer_id=layer_id,
                        client=client,
                        model_size=gen.model_size,
                        seed=layer_seed,
                    )
                except Exception as exc:
                    print(f"FAILED {label}/{layer_id}: {exc}")
                    failures += 1
                    continue
                print(f"  wrote {dest}")

        if failures:
            print(f"Done with {failures} failure(s).")
            return 1
        print("Done.")
        return 0
    finally:
        lifecycle.stop_owned()


if __name__ == "__main__":
    sys.exit(main())

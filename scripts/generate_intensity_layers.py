"""Generate MusicGen intensity layers (texture, melody_b) for a song family."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from adaptive_soundscape.audio.generate_layers import generate_and_install_layer
from adaptive_soundscape.audio.musicgen_client import MusicGenClient
from adaptive_soundscape.core.config import load_settings, resolve_assets_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, help="Scenario profile id")
    parser.add_argument("--song", required=True, help="Song folder name")
    parser.add_argument(
        "--layers",
        default="",
        help="Comma-separated layer ids (default: config generative_layers.output_layers)",
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    settings = load_settings()
    gen = settings.generative_layers
    if not gen.enabled:
        print("generative_layers.enabled is false in config")
        return 1
    assets = resolve_assets_dir(settings)
    song_dir = assets / args.scenario / args.song
    if not (song_dir / "manifest.json").is_file():
        print(f"Song not found: {song_dir}")
        return 1

    layers = [x.strip() for x in args.layers.split(",") if x.strip()]
    if not layers:
        layers = list(gen.output_layers)

    client = MusicGenClient(gen.api_base_url, timeout_seconds=gen.timeout_seconds)
    try:
        health = client.health()
        print(f"API health: {health}")
    except RuntimeError as exc:
        print(exc)
        return 1

    for layer_id in layers:
        print(f"Generating {layer_id} …")
        try:
            dest = generate_and_install_layer(
                song_dir,
                scenario=args.scenario,
                layer_id=layer_id,
                client=client,
                model_size=gen.model_size,
                seed=args.seed,
            )
        except Exception as exc:
            print(f"FAILED {layer_id}: {exc}")
            return 1
        print(f"  wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

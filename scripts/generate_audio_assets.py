"""CLI wrapper for audio asset generation."""

import argparse
from pathlib import Path

from adaptive_soundscape.audio.asset_generator import ensure_assets, generate_all, generate_pads


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate placeholder WAV loops")
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "audio",
    )
    parser.add_argument(
        "--pads-only",
        action="store_true",
        help="Generate only *_pad.wav files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files",
    )
    args = parser.parse_args()
    if args.pads_only:
        written = generate_pads(args.assets_dir, overwrite=args.force)
    elif args.force:
        written = generate_all(args.assets_dir, overwrite=True)
    else:
        written = ensure_assets(args.assets_dir)
    print(f"Wrote {len(written)} file(s) under {args.assets_dir}")


if __name__ == "__main__":
    main()

"""Generate pad-layer WAV files (`{profile}_pad.wav`) for all context profiles."""

from __future__ import annotations

import argparse
from pathlib import Path

from adaptive_soundscape.audio.asset_generator import generate_pads_from_sources


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate missing pad underlayer loops in assets/audio/"
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "audio",
        help="Directory for WAV output (default: assets/audio)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing pad files",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use synthetic sine pads instead of deriving from main audio",
    )
    args = parser.parse_args()
    if args.synthetic:
        from adaptive_soundscape.audio.asset_generator import PROFILES, _render_pad, write_wav

        written = []
        for profile_id, (fa, fb, amp) in PROFILES.items():
            path = args.assets_dir / f"{profile_id}_pad.wav"
            if path.exists() and not args.force:
                continue
            pad = _render_pad(fa * 0.5, fb * 0.5, amp * 0.6, 60)
            write_wav(path, pad)
            written.append(path)
    else:
        written = generate_pads_from_sources(args.assets_dir, overwrite=args.force)
    if written:
        print(f"Generated {len(written)} pad file(s):")
        for path in written:
            print(f"  {path}")
    else:
        print("All pad files already exist (use --force to regenerate).")


if __name__ == "__main__":
    main()

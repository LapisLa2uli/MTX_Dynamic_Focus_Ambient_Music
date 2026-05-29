"""CLI wrapper for audio asset generation."""

from pathlib import Path

from adaptive_soundscape.audio.asset_generator import generate_all

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    generate_all(root / "assets" / "audio")
    print("Generated placeholder audio in assets/audio/")

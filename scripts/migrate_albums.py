"""One-shot migration: flat assets/audio/*.mp3 → per-scenario albums."""

from pathlib import Path

from adaptive_soundscape.audio.album import PROFILE_IDS, ensure_albums, list_tracks


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "audio"
    created = ensure_albums(root, prefer_mp3=True)
    print(f"created/migrated: {len(created)}")
    for profile_id in PROFILE_IDS:
        tracks = list_tracks(root, profile_id)
        print(f"  {profile_id}: {[t.name for t in tracks]}")


if __name__ == "__main__":
    main()

"""Migrate flat album tracks into nested intensity song families + layered stubs."""

from pathlib import Path

from adaptive_soundscape.audio.album import PROFILE_IDS, ensure_albums, list_songs
from adaptive_soundscape.audio.layer_mix import LAYER_IDS
from adaptive_soundscape.audio.music_manifest import (
    MusicIntensity,
    list_playable_tracks,
    load_manifest,
)


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "assets" / "audio"
    created = ensure_albums(root, prefer_mp3=True)
    print(f"created/migrated: {len(created)}")
    for profile_id in PROFILE_IDS:
        songs = list_songs(root, profile_id)
        print(f"  {profile_id}:")
        for song in songs:
            counts = {
                intensity.value: len(list_playable_tracks(song, intensity))
                for intensity in MusicIntensity
            }
            manifest = load_manifest(song)
            layers = {}
            if manifest is not None:
                layers = {
                    lid: 1 if lid in manifest.playable_layer_paths(song) else 0
                    for lid in LAYER_IDS
                }
            mode = manifest.playback_mode if manifest else "?"
            print(f"    {song.name}: mode={mode} intensity={counts} layers={layers}")


if __name__ == "__main__":
    main()

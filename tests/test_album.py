"""Tests for per-scenario song albums and nested intensity families."""

from pathlib import Path
import wave

import numpy as np

from adaptive_soundscape.audio.album import (
    PROFILE_IDS,
    add_track,
    delete_track,
    ensure_albums,
    list_songs,
    list_tracks,
    migrate_flat_assets_to_albums,
    pick_random_song,
)
from adaptive_soundscape.audio.music_manifest import (
    MusicIntensity,
    list_playable_tracks,
    load_manifest,
)


def _write_sine_wav(path: Path, seconds: float = 0.2, rate: int = 44100) -> None:
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    samples = (0.2 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())


def test_migrate_flat_creates_one_song_per_album(tmp_path: Path):
    _write_sine_wav(tmp_path / "programming.wav")
    _write_sine_wav(tmp_path / "scientific.wav")
    created = migrate_flat_assets_to_albums(tmp_path, prefer_mp3=False)
    assert len(created) >= 2
    written = ensure_albums(tmp_path, prefer_mp3=False)
    assert written
    assert list_songs(tmp_path, "programming")
    assert list_songs(tmp_path, "scientific")
    song = list_songs(tmp_path, "programming")[0]
    assert load_manifest(song) is not None
    assert list_playable_tracks(song, MusicIntensity.FOCUS)


def test_ensure_albums_fills_empty_profiles(tmp_path: Path):
    ensure_albums(tmp_path, prefer_mp3=False)
    for profile_id in PROFILE_IDS:
        assert list_songs(tmp_path, profile_id) or list_tracks(tmp_path, profile_id), profile_id


def test_pick_random_song(tmp_path: Path):
    ensure_albums(tmp_path, prefer_mp3=False)
    song = pick_random_song(tmp_path, "programming")
    assert song is not None
    assert song.is_dir()


def test_add_and_delete_intensity_track(tmp_path: Path):
    src = tmp_path / "upload.wav"
    _write_sine_wav(src)
    dest = add_track(tmp_path, "creative_design", src, intensity=MusicIntensity.FOCUS)
    assert dest.exists()
    song = dest.parent.parent
    assert load_manifest(song) is not None
    src2 = tmp_path / "upload2.wav"
    _write_sine_wav(src2)
    add_track(
        tmp_path,
        "creative_design",
        src2,
        intensity=MusicIntensity.CALM,
        song_id=song.name,
    )
    delete_track(dest)
    assert not dest.exists()

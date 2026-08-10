"""Tests for per-scenario song albums."""

from pathlib import Path
import wave

import numpy as np

from adaptive_soundscape.audio.album import (
    PROFILE_IDS,
    add_track,
    delete_track,
    ensure_albums,
    list_tracks,
    migrate_flat_assets_to_albums,
    pick_random_track,
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
    assert len(list_tracks(tmp_path, "programming")) == 1
    assert len(list_tracks(tmp_path, "scientific")) == 1


def test_ensure_albums_fills_empty_profiles(tmp_path: Path):
    ensure_albums(tmp_path, prefer_mp3=False)
    for profile_id in PROFILE_IDS:
        assert list_tracks(tmp_path, profile_id), profile_id


def test_pick_random_avoids_exclude_when_possible(tmp_path: Path):
    album = tmp_path / "programming"
    album.mkdir()
    a = album / "a.wav"
    b = album / "b.wav"
    _write_sine_wav(a)
    _write_sine_wav(b)
    for _ in range(10):
        pick = pick_random_track(tmp_path, "programming", exclude=a)
        assert pick == b


def test_add_and_delete_track(tmp_path: Path):
    src = tmp_path / "upload.wav"
    _write_sine_wav(src)
    dest = add_track(tmp_path, "creative_design", src)
    assert dest.exists()
    assert dest in list_tracks(tmp_path, "creative_design")
    # Keep album non-empty: add a second then delete first.
    src2 = tmp_path / "upload2.wav"
    _write_sine_wav(src2)
    add_track(tmp_path, "creative_design", src2)
    delete_track(dest)
    assert dest not in list_tracks(tmp_path, "creative_design")

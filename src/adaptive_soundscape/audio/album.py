"""Per-scenario song albums (nested intensity song families)."""

from __future__ import annotations

import logging
import random
import re
import shutil
from pathlib import Path

from adaptive_soundscape.audio.loader import SUPPORTED_EXTENSIONS, resolve_asset
from adaptive_soundscape.audio.layer_mix import LAYER_IDS
from adaptive_soundscape.audio.music_manifest import (
    MANIFEST_NAME,
    MusicIntensity,
    build_manifest_for_song,
    list_playable_tracks,
    load_manifest,
    save_manifest,
    song_dirs,
)
from adaptive_soundscape.audio.profiles import CONTEXT_PROFILES

logger = logging.getLogger(__name__)

PROFILE_IDS: tuple[str, ...] = tuple(
    sorted({profile.profile_id for profile in CONTEXT_PROFILES.values()})
)

STEM_LAYER_NAMES: frozenset[str] = frozenset(
    {"ambient", "rhythm", "harmonic", "accent"}
)


def album_dir(assets_dir: Path, profile_id: str) -> Path:
    return assets_dir / profile_id


def list_songs(assets_dir: Path, profile_id: str) -> list[Path]:
    """Return song-family directories (with manifests) in a scenario album."""
    return [
        d
        for d in song_dirs(assets_dir, profile_id)
        if (d / MANIFEST_NAME).is_file() or any(d.iterdir())
    ]


def list_tracks(assets_dir: Path, profile_id: str) -> list[Path]:
    """
    Legacy helper: flat audio files OR representative focus track paths for songs.

    Prefer ``list_songs`` for the nested intensity model.
    """
    folder = album_dir(assets_dir, profile_id)
    if not folder.is_dir():
        return []
    tracks: list[Path] = []
    for path in sorted(folder.iterdir()):
        if path.is_dir():
            playable = list_playable_tracks(path, MusicIntensity.FOCUS)
            if playable:
                tracks.append(playable[0][1])
                continue
            # Any intensity
            for intensity in MusicIntensity:
                playable = list_playable_tracks(path, intensity)
                if playable:
                    tracks.append(playable[0][1])
                    break
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if path.stem.lower() in STEM_LAYER_NAMES:
            continue
        if path.stem.lower().endswith("_pad"):
            continue
        tracks.append(path)
    return tracks


def pick_random_song(
    assets_dir: Path,
    profile_id: str,
    *,
    exclude: Path | None = None,
    rng: random.Random | None = None,
) -> Path | None:
    """Pick a random song-family directory from the scenario album."""
    songs = list_songs(assets_dir, profile_id)
    if not songs:
        return None
    chooser = rng or random
    if exclude is not None and len(songs) > 1:
        alternatives = [s for s in songs if s.resolve() != exclude.resolve()]
        if alternatives:
            songs = alternatives
    return chooser.choice(songs)


def pick_random_track(
    assets_dir: Path,
    profile_id: str,
    *,
    exclude: Path | None = None,
    rng: random.Random | None = None,
) -> Path | None:
    """Pick a playable focus (or any) track path from a random song."""
    song = pick_random_song(assets_dir, profile_id, exclude=None, rng=rng)
    if song is None:
        # Fall back to flat files
        tracks = [
            p
            for p in list_tracks(assets_dir, profile_id)
            if p.is_file() and p.parent == album_dir(assets_dir, profile_id)
        ]
        if not tracks:
            return None
        chooser = rng or random
        if exclude is not None and len(tracks) > 1:
            alternatives = [t for t in tracks if t.resolve() != exclude.resolve()]
            if alternatives:
                tracks = alternatives
        return chooser.choice(tracks)
    for intensity in (
        MusicIntensity.FOCUS,
        MusicIntensity.CALM,
        MusicIntensity.DEEP_FOCUS,
        MusicIntensity.RECOVERY,
    ):
        playable = list_playable_tracks(song, intensity)
        if not playable:
            continue
        paths = [p for _, p in playable]
        chooser = rng or random
        if exclude is not None and len(paths) > 1:
            alternatives = [p for p in paths if p.resolve() != exclude.resolve()]
            if alternatives:
                paths = alternatives
        return chooser.choice(paths)
    return None


def add_track(
    assets_dir: Path,
    profile_id: str,
    source: Path,
    *,
    intensity: MusicIntensity = MusicIntensity.FOCUS,
    song_id: str | None = None,
) -> Path:
    """
    Add audio into a song family intensity bucket.

    Creates a new song folder when ``song_id`` is omitted.
    """
    if profile_id not in PROFILE_IDS:
        raise ValueError(f"Unknown scenario profile: {profile_id}")
    if not source.is_file():
        raise FileNotFoundError(f"Audio file not found: {source}")
    ext = source.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported audio format: {ext} (use .mp3 or .wav)")

    folder = album_dir(assets_dir, profile_id)
    folder.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(song_id or source.stem)
    song_dir = folder / stem
    counter = 2
    while song_dir.exists() and song_id is None:
        song_dir = folder / f"{stem}_{counter}"
        counter += 1
    song_dir.mkdir(parents=True, exist_ok=True)
    intensity_dir = song_dir / intensity.value
    intensity_dir.mkdir(parents=True, exist_ok=True)

    track_stem = f"{intensity.value}_01"
    dest = intensity_dir / f"{track_stem}{ext}"
    n = 2
    while dest.exists():
        dest = intensity_dir / f"{intensity.value}_{n:02d}{ext}"
        n += 1
    shutil.copy2(source, dest)

    manifest = load_manifest(song_dir)
    rel = f"{intensity.value}/{dest.name}"
    if manifest is None:
        kwargs = {
            "focus_rel": rel if intensity == MusicIntensity.FOCUS else None,
            "calm_rel": rel if intensity == MusicIntensity.CALM else None,
            "deep_rel": rel if intensity == MusicIntensity.DEEP_FOCUS else None,
            "recovery_rel": rel if intensity == MusicIntensity.RECOVERY else None,
        }
        # Prefer at least a focus entry pointing at the file if not focus.
        if intensity != MusicIntensity.FOCUS:
            kwargs["focus_rel"] = rel
        manifest = build_manifest_for_song(song_dir.name, **kwargs)  # type: ignore[arg-type]
    else:
        from adaptive_soundscape.audio.music_manifest import StateTracks, TrackEntry, _state_key

        key = _state_key(intensity)
        bucket = manifest.states.setdefault(key, StateTracks())
        track_id = dest.stem
        if not any(t.id == track_id for t in bucket.tracks):
            bucket.tracks.append(TrackEntry(id=track_id, src=rel))
    save_manifest(song_dir, manifest)
    logger.info("Added album track %s → %s", source.name, dest)
    return dest


def delete_track(path: Path) -> None:
    """Delete a track file (and prune intensity/layer entries from manifest)."""
    if not path.is_file():
        raise FileNotFoundError(f"Track not found: {path}")
    parent_name = path.parent.name
    intensity_names = {i.value for i in MusicIntensity}
    if parent_name in intensity_names or parent_name in LAYER_IDS:
        song_dir = path.parent.parent
    else:
        song_dir = path.parent
    path.unlink()
    logger.info("Deleted album track %s", path)
    manifest = load_manifest(song_dir)
    if manifest is None:
        return
    changed = False
    for key, bucket in list(manifest.states.items()):
        kept = []
        for entry in bucket.tracks:
            resolved = (song_dir / entry.src).resolve()
            if resolved == path.resolve() or not resolved.is_file():
                changed = True
                continue
            kept.append(entry)
        bucket.tracks = kept
    for lid, entry in list(manifest.layers.items()):
        resolved = (song_dir / entry.src).resolve()
        if resolved == path.resolve() or not resolved.is_file():
            del manifest.layers[lid]
            changed = True
    if changed:
        save_manifest(song_dir, manifest)


def migrate_flat_assets_to_albums(assets_dir: Path, *, prefer_mp3: bool = True) -> list[Path]:
    """Ensure each scenario album exists and contains at least one flat or song asset."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for profile_id in PROFILE_IDS:
        folder = album_dir(assets_dir, profile_id)
        folder.mkdir(parents=True, exist_ok=True)
        if list_songs(assets_dir, profile_id) or list_tracks(assets_dir, profile_id):
            continue
        flat = resolve_asset(assets_dir, profile_id, prefer_mp3=prefer_mp3)
        if flat is None:
            continue
        dest = folder / f"{profile_id}_01{flat.suffix.lower()}"
        if not dest.exists():
            shutil.copy2(flat, dest)
            created.append(dest)
            logger.info("Migrated flat asset %s → %s", flat.name, dest)
    return created


def ensure_albums(assets_dir: Path, *, prefer_mp3: bool = True) -> list[Path]:
    """Migrate flat assets, synthesize missing albums, then nest into song families."""
    from adaptive_soundscape.audio.asset_generator import (
        PROFILES,
        _render_pad,
        write_wav,
    )
    from adaptive_soundscape.audio.music_manifest import (
        migrate_flat_tracks_to_song_families,
        migrate_songs_to_layered_stubs,
    )

    written = migrate_flat_assets_to_albums(assets_dir, prefer_mp3=prefer_mp3)
    for profile_id in PROFILE_IDS:
        if list_songs(assets_dir, profile_id) or list_tracks(assets_dir, profile_id):
            continue
        fa, fb, amp = PROFILES.get(profile_id, (110.0, 220.0, 0.08))
        folder = album_dir(assets_dir, profile_id)
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{profile_id}_01.wav"
        if dest.exists():
            continue
        write_wav(dest, _render_pad(fa, fb, amp, 60.0))
        written.append(dest)
        logger.info("Generated placeholder album track %s", dest)
    written.extend(migrate_flat_tracks_to_song_families(assets_dir))
    written.extend(migrate_songs_to_layered_stubs(assets_dir))
    return written


def add_layer_track(
    assets_dir: Path,
    profile_id: str,
    source: Path,
    *,
    layer_id: str,
    song_id: str,
) -> Path:
    """Add or replace a stem layer file inside an existing song family."""
    from adaptive_soundscape.audio.music_manifest import LayerEntry

    if profile_id not in PROFILE_IDS:
        raise ValueError(f"Unknown scenario profile: {profile_id}")
    if layer_id not in LAYER_IDS:
        raise ValueError(f"Unknown layer id: {layer_id}")
    if not source.is_file():
        raise FileNotFoundError(f"Audio file not found: {source}")
    ext = source.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported audio format: {ext} (use .mp3 or .wav)")

    song_dir = album_dir(assets_dir, profile_id) / _safe_stem(song_id)
    song_dir.mkdir(parents=True, exist_ok=True)
    layer_dir = song_dir / layer_id
    layer_dir.mkdir(parents=True, exist_ok=True)
    dest = layer_dir / f"{layer_id}_01{ext}"
    n = 2
    while dest.exists():
        dest = layer_dir / f"{layer_id}_{n:02d}{ext}"
        n += 1
    shutil.copy2(source, dest)

    manifest = load_manifest(song_dir)
    rel = f"{layer_id}/{dest.name}"
    if manifest is None:
        manifest = build_manifest_for_song(song_dir.name, focus_rel="")
    generated = layer_id in {"melody_b", "texture"}
    manifest.layers[layer_id] = LayerEntry(
        src=rel,
        role="intensity" if generated else "base",
        generated=generated,
        baseGain=0.75,
    )
    manifest.playback_mode = "layered"
    save_manifest(song_dir, manifest)
    logger.info("Added layer %s → %s", layer_id, dest)
    return dest


def display_name_for_profile(profile_id: str) -> str:
    for profile in CONTEXT_PROFILES.values():
        if profile.profile_id == profile_id:
            return profile.display_name
    return profile_id.replace("_", " ").title()


def _safe_stem(stem: str) -> str:
    cleaned = re.sub(r"[^\w\-]+", "_", stem.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("_") or "track"
    return cleaned[:80]

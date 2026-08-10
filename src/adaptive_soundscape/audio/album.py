"""Per-scenario song albums with random track selection."""

from __future__ import annotations

import logging
import random
import re
import shutil
from pathlib import Path

from adaptive_soundscape.audio.loader import SUPPORTED_EXTENSIONS, resolve_asset
from adaptive_soundscape.audio.profiles import CONTEXT_PROFILES

logger = logging.getLogger(__name__)

PROFILE_IDS: tuple[str, ...] = tuple(
    sorted({profile.profile_id for profile in CONTEXT_PROFILES.values()})
)

# Legacy Godot stem filenames — not treated as album "songs".
STEM_LAYER_NAMES: frozenset[str] = frozenset(
    {"ambient", "rhythm", "harmonic", "accent"}
)


def album_dir(assets_dir: Path, profile_id: str) -> Path:
    return assets_dir / profile_id


def list_tracks(assets_dir: Path, profile_id: str) -> list[Path]:
    """Return song files in the scenario album (sorted by name)."""
    folder = album_dir(assets_dir, profile_id)
    if not folder.is_dir():
        return []
    tracks: list[Path] = []
    for path in sorted(folder.iterdir()):
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


def pick_random_track(
    assets_dir: Path,
    profile_id: str,
    *,
    exclude: Path | None = None,
    rng: random.Random | None = None,
) -> Path | None:
    """Pick a random song from the album; avoid ``exclude`` when alternatives exist."""
    tracks = list_tracks(assets_dir, profile_id)
    if not tracks:
        return None
    chooser = rng or random
    if exclude is not None and len(tracks) > 1:
        alternatives = [t for t in tracks if t.resolve() != exclude.resolve()]
        if alternatives:
            tracks = alternatives
    return chooser.choice(tracks)


def add_track(assets_dir: Path, profile_id: str, source: Path) -> Path:
    """Copy ``source`` into the scenario album with a unique filename."""
    if profile_id not in PROFILE_IDS:
        raise ValueError(f"Unknown scenario profile: {profile_id}")
    if not source.is_file():
        raise FileNotFoundError(f"Audio file not found: {source}")
    ext = source.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported audio format: {ext} (use .mp3 or .wav)")

    folder = album_dir(assets_dir, profile_id)
    folder.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(source.stem)
    dest = folder / f"{stem}{ext}"
    counter = 2
    while dest.exists():
        dest = folder / f"{stem}_{counter}{ext}"
        counter += 1
    shutil.copy2(source, dest)
    logger.info("Added album track %s → %s", source.name, dest)
    return dest


def delete_track(path: Path) -> None:
    """Delete a track file from an album."""
    if not path.is_file():
        raise FileNotFoundError(f"Track not found: {path}")
    path.unlink()
    logger.info("Deleted album track %s", path)


def migrate_flat_assets_to_albums(assets_dir: Path, *, prefer_mp3: bool = True) -> list[Path]:
    """
    Ensure each scenario album exists and contains at least one song.

    Copies the preferred flat ``{profile}.mp3/.wav`` into the album when empty.
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for profile_id in PROFILE_IDS:
        folder = album_dir(assets_dir, profile_id)
        folder.mkdir(parents=True, exist_ok=True)
        if list_tracks(assets_dir, profile_id):
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
    """Migrate flat assets, then synthesize a song for any still-empty album."""
    from adaptive_soundscape.audio.asset_generator import (
        PROFILES,
        _render_pad,
        write_wav,
    )

    written = migrate_flat_assets_to_albums(assets_dir, prefer_mp3=prefer_mp3)
    for profile_id in PROFILE_IDS:
        if list_tracks(assets_dir, profile_id):
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
    return written


def display_name_for_profile(profile_id: str) -> str:
    for profile in CONTEXT_PROFILES.values():
        if profile.profile_id == profile_id:
            return profile.display_name
    return profile_id.replace("_", " ").title()


def _safe_stem(stem: str) -> str:
    cleaned = re.sub(r"[^\w\-]+", "_", stem.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("_") or "track"
    return cleaned[:80]

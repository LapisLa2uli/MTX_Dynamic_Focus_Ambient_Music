"""Song-family manifests: intensity loops + optional layered stems."""

from __future__ import annotations

import json
import logging
import shutil
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from adaptive_soundscape.audio.layer_mix import BASE_LAYER_IDS, LAYER_IDS
from adaptive_soundscape.audio.loader import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"
INTENSITY_DIRS: tuple[str, ...] = ("calm", "focus", "deep_focus", "recovery")


class MusicIntensity(str, Enum):
    CALM = "calm"
    FOCUS = "focus"
    DEEP_FOCUS = "deep_focus"
    RECOVERY = "recovery"


class PlaybackMode(str, Enum):
    LAYERED = "layered"
    DISCRETE = "discrete"


class TrackEntry(BaseModel):
    id: str
    src: str
    loop_start_ms: int = Field(default=0, alias="loopStartMs")
    loop_end_ms: int | None = Field(default=None, alias="loopEndMs")

    model_config = {"populate_by_name": True}


class StateTracks(BaseModel):
    tracks: list[TrackEntry] = Field(default_factory=list)


class LayerEntry(BaseModel):
    src: str
    role: str = "base"
    generated: bool = False
    base_gain: float = Field(default=0.75, alias="baseGain")

    model_config = {"populate_by_name": True}


class SongManifest(BaseModel):
    song_id: str = Field(alias="songId")
    bpm: float = 70.0
    time_signature: str = Field(default="4/4", alias="timeSignature")
    bars_per_loop: int = Field(default=8, alias="barsPerLoop")
    crossfade_ms: int = Field(default=1500, alias="crossfadeMs")
    loop_seconds: float = Field(default=27.428, alias="loopSeconds")
    playback_mode: str = Field(default="layered", alias="playbackMode")
    layers: dict[str, LayerEntry] = Field(default_factory=dict)
    states: dict[str, StateTracks] = Field(default_factory=dict)
    transitions: dict[str, str] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    def state_tracks(self, intensity: MusicIntensity) -> list[TrackEntry]:
        key = _state_key(intensity)
        bucket = self.states.get(key) or self.states.get(intensity.value)
        if bucket is None:
            return []
        return list(bucket.tracks)

    def resolve_track_path(self, song_dir: Path, track: TrackEntry) -> Path:
        return (song_dir / track.src).resolve()

    def resolve_layer_path(self, song_dir: Path, layer_id: str) -> Path | None:
        entry = self.layers.get(layer_id)
        if entry is None:
            return None
        path = (song_dir / entry.src).resolve()
        return path if path.is_file() else None

    def playable_layer_paths(self, song_dir: Path) -> dict[str, Path]:
        out: dict[str, Path] = {}
        for layer_id in LAYER_IDS:
            path = self.resolve_layer_path(song_dir, layer_id)
            if path is not None:
                out[layer_id] = path
        return out

    def prefers_layered(self, song_dir: Path) -> bool:
        """True when layered mode is requested and ≥2 base layers exist."""
        mode = (self.playback_mode or "layered").lower()
        if mode == PlaybackMode.DISCRETE.value:
            return False
        playable = self.playable_layer_paths(song_dir)
        base_count = sum(1 for lid in BASE_LAYER_IDS if lid in playable)
        return base_count >= 2

    def transition_src(self, from_state: MusicIntensity, to_state: MusicIntensity) -> str | None:
        key = f"{_state_key(from_state)}->{_state_key(to_state)}"
        alt = f"{from_state.value}->{to_state.value}"
        return self.transitions.get(key) or self.transitions.get(alt)


def _state_key(intensity: MusicIntensity) -> str:
    if intensity == MusicIntensity.DEEP_FOCUS:
        return "deepFocus"
    return intensity.value


def song_dirs(assets_dir: Path, profile_id: str) -> list[Path]:
    """Return song-family directories under a scenario album."""
    album = assets_dir / profile_id
    if not album.is_dir():
        return []
    dirs: list[Path] = []
    for path in sorted(album.iterdir()):
        if path.is_dir() and not path.name.startswith("."):
            dirs.append(path)
    return dirs


def load_manifest(song_dir: Path) -> SongManifest | None:
    path = song_dir / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return SongManifest.model_validate(data)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Invalid song manifest %s: %s", path, exc)
        return None


def save_manifest(song_dir: Path, manifest: SongManifest) -> Path:
    song_dir.mkdir(parents=True, exist_ok=True)
    path = song_dir / MANIFEST_NAME
    payload = manifest.model_dump(by_alias=True, exclude_none=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def build_manifest_for_song(
    song_id: str,
    *,
    focus_rel: str,
    calm_rel: str | None = None,
    deep_rel: str | None = None,
    recovery_rel: str | None = None,
    crossfade_ms: int = 1500,
) -> SongManifest:
    states: dict[str, StateTracks] = {
        "calm": StateTracks(tracks=[]),
        "focus": StateTracks(tracks=[]),
        "deepFocus": StateTracks(tracks=[]),
        "recovery": StateTracks(tracks=[]),
    }
    if calm_rel:
        states["calm"].tracks.append(TrackEntry(id="calm_01", src=calm_rel))
    if focus_rel:
        states["focus"].tracks.append(TrackEntry(id="focus_01", src=focus_rel))
    if deep_rel:
        states["deepFocus"].tracks.append(TrackEntry(id="deep_focus_01", src=deep_rel))
    if recovery_rel:
        states["recovery"].tracks.append(TrackEntry(id="recovery_01", src=recovery_rel))
    return SongManifest(
        songId=song_id,
        bpm=70,
        timeSignature="4/4",
        barsPerLoop=8,
        crossfadeMs=crossfade_ms,
        loopSeconds=27.428,
        playbackMode="layered",
        layers={},
        states=states,
        transitions={},
    )


def _seed_source_for_layers(song_dir: Path, manifest: SongManifest) -> Path | None:
    """Pick a representative discrete loop to stub layered stems from."""
    for intensity in (
        MusicIntensity.FOCUS,
        MusicIntensity.CALM,
        MusicIntensity.DEEP_FOCUS,
        MusicIntensity.RECOVERY,
    ):
        playable = list_playable_tracks(song_dir, intensity)
        if playable:
            return playable[0][1]
    for path in sorted(song_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            if path.name == MANIFEST_NAME:
                continue
            return path
    return None


def migrate_songs_to_layered_stubs(assets_dir: Path) -> list[Path]:
    """
    Ensure each song family has pad/harmony/melody_a/rhythm stubs.

    Copies the focus (or first available) loop into base layer folders when missing.
    Discrete intensity folders are left intact for fallback.
    """
    created: list[Path] = []
    if not assets_dir.is_dir():
        return created
    for scenario_dir in sorted(p for p in assets_dir.iterdir() if p.is_dir()):
        for song_dir in song_dirs(assets_dir, scenario_dir.name):
            manifest = load_manifest(song_dir)
            if manifest is None:
                continue
            if manifest.prefers_layered(song_dir):
                # Still refresh playbackMode default if layers already complete.
                if (manifest.playback_mode or "").lower() != "layered":
                    manifest.playback_mode = "layered"
                    save_manifest(song_dir, manifest)
                    created.append(song_dir / MANIFEST_NAME)
                continue
            seed = _seed_source_for_layers(song_dir, manifest)
            if seed is None:
                continue
            ext = seed.suffix.lower()
            for layer_id in BASE_LAYER_IDS:
                layer_dir = song_dir / layer_id
                layer_dir.mkdir(parents=True, exist_ok=True)
                dest = layer_dir / f"{layer_id}_01{ext}"
                if not dest.exists():
                    shutil.copy2(seed, dest)
                    created.append(dest)
                rel = f"{layer_id}/{dest.name}"
                if layer_id not in manifest.layers:
                    manifest.layers[layer_id] = LayerEntry(
                        src=rel,
                        role="base",
                        generated=False,
                        baseGain=0.75,
                    )
                else:
                    entry = manifest.layers[layer_id]
                    if not (song_dir / entry.src).is_file():
                        entry.src = rel
            # Optional empty dirs for AI outputs
            for layer_id in ("melody_b", "texture", "recovery"):
                (song_dir / layer_id).mkdir(exist_ok=True)
            manifest.playback_mode = "layered"
            if manifest.loop_seconds <= 0:
                manifest.loop_seconds = 27.428
            save_manifest(song_dir, manifest)
            created.append(song_dir / MANIFEST_NAME)
            logger.info("Migrated song %s → layered stubs", song_dir)
    return created


def migrate_flat_tracks_to_song_families(assets_dir: Path) -> list[Path]:
    """
    Convert legacy flat ``{scenario}/{name}.mp3`` files into song folders
    with intensity variants (focus real; calm/deep_focus copy placeholders).
    """
    created: list[Path] = []
    if not assets_dir.is_dir():
        return created
    for scenario_dir in sorted(p for p in assets_dir.iterdir() if p.is_dir()):
        for path in sorted(scenario_dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if path.stem.lower().endswith("_pad"):
                continue
            song_dir = scenario_dir / path.stem
            if song_dir.is_dir() and (song_dir / MANIFEST_NAME).is_file():
                continue
            song_dir.mkdir(parents=True, exist_ok=True)
            for intensity in INTENSITY_DIRS:
                (song_dir / intensity).mkdir(exist_ok=True)
            (song_dir / "transitions").mkdir(exist_ok=True)

            ext = path.suffix.lower()
            focus_name = f"focus_01{ext}"
            focus_dest = song_dir / "focus" / focus_name
            if not focus_dest.exists():
                shutil.copy2(path, focus_dest)
                created.append(focus_dest)

            # Compatible placeholders until distinct intensity loops are authored.
            for intensity, track_name in (
                ("calm", f"calm_01{ext}"),
                ("deep_focus", f"deep_focus_01{ext}"),
            ):
                dest = song_dir / intensity / track_name
                if not dest.exists():
                    shutil.copy2(path, dest)
                    created.append(dest)

            manifest = build_manifest_for_song(
                path.stem,
                focus_rel=f"focus/{focus_name}",
                calm_rel=f"calm/calm_01{ext}",
                deep_rel=f"deep_focus/deep_focus_01{ext}",
            )
            save_manifest(song_dir, manifest)
            created.append(song_dir / MANIFEST_NAME)
            logger.info("Migrated flat track %s → song family %s", path.name, song_dir)
    return created


def ensure_song_families(assets_dir: Path, *, prefer_mp3: bool = True) -> list[Path]:
    """Ensure albums exist, then migrate flats into nested song families."""
    from adaptive_soundscape.audio.album import ensure_albums

    written = ensure_albums(assets_dir, prefer_mp3=prefer_mp3)
    written.extend(migrate_flat_tracks_to_song_families(assets_dir))
    written.extend(migrate_songs_to_layered_stubs(assets_dir))
    return written


def list_playable_tracks(
    song_dir: Path, intensity: MusicIntensity
) -> list[tuple[TrackEntry, Path]]:
    """Return (entry, absolute path) pairs that exist on disk for a state."""
    manifest = load_manifest(song_dir)
    if manifest is None:
        return []
    out: list[tuple[TrackEntry, Path]] = []
    for entry in manifest.state_tracks(intensity):
        path = manifest.resolve_track_path(song_dir, entry)
        if path.is_file():
            out.append((entry, path))
    return out


def nearest_available_intensity(
    song_dir: Path, desired: MusicIntensity
) -> MusicIntensity | None:
    """Fall back across intensities when the desired state has no files."""
    order = {
        MusicIntensity.CALM: [
            MusicIntensity.CALM,
            MusicIntensity.FOCUS,
            MusicIntensity.DEEP_FOCUS,
            MusicIntensity.RECOVERY,
        ],
        MusicIntensity.FOCUS: [
            MusicIntensity.FOCUS,
            MusicIntensity.CALM,
            MusicIntensity.DEEP_FOCUS,
            MusicIntensity.RECOVERY,
        ],
        MusicIntensity.DEEP_FOCUS: [
            MusicIntensity.DEEP_FOCUS,
            MusicIntensity.FOCUS,
            MusicIntensity.CALM,
            MusicIntensity.RECOVERY,
        ],
        MusicIntensity.RECOVERY: [
            MusicIntensity.RECOVERY,
            MusicIntensity.CALM,
            MusicIntensity.FOCUS,
            MusicIntensity.DEEP_FOCUS,
        ],
    }
    for candidate in order[desired]:
        if list_playable_tracks(song_dir, candidate):
            return candidate
    return None

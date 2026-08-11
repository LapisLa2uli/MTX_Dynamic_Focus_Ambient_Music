"""Offline orchestration: seed mix → Demucs API → base layer stems."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from adaptive_soundscape.audio.demucs_client import DemucsClient
from adaptive_soundscape.audio.layer_mix import BASE_LAYER_IDS
from adaptive_soundscape.audio.music_manifest import (
    LayerEntry,
    _seed_source_for_layers,
    load_manifest,
    save_manifest,
)

logger = logging.getLogger(__name__)

SEPARATION_META_NAME = "separation_meta.json"
VOCALS_SILENCE_RMS = 1e-3


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _layer_file(song_dir: Path, layer_id: str) -> Path | None:
    manifest = load_manifest(song_dir)
    if manifest is not None and layer_id in manifest.layers:
        candidate = song_dir / manifest.layers[layer_id].src
        if candidate.is_file():
            return candidate
    layer_dir = song_dir / layer_id
    if not layer_dir.is_dir():
        return None
    for path in sorted(layer_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in {".wav", ".mp3"}:
            return path
    return None


def needs_separation(song_dir: Path, *, force: bool = False) -> bool:
    """True if base layers are missing, stub copies of the seed, or never separated."""
    if force:
        return True
    meta_path = song_dir / SEPARATION_META_NAME
    if meta_path.is_file():
        # Already separated successfully unless force.
        return False

    manifest = load_manifest(song_dir)
    if manifest is None:
        return False
    seed = _seed_source_for_layers(song_dir, manifest)
    if seed is None:
        return False

    present: list[Path] = []
    for layer_id in BASE_LAYER_IDS:
        path = _layer_file(song_dir, layer_id)
        if path is None:
            return True
        present.append(path)

    seed_hash = file_sha256(seed)
    # Stub detection: every base layer is a byte-identical copy of the seed.
    if all(file_sha256(p) == seed_hash for p in present):
        return True
    # Distinct user-provided stems without meta — do not overwrite.
    return False


def _wav_rms(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.getnframes()
        raw = wf.readframes(frames)
    if frames <= 0 or rate <= 0:
        return 0.0
    if sw == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
    if nch > 1:
        samples = samples.reshape(-1, nch).mean(axis=1)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples * samples)))


def _highpass_wav(wav_bytes: bytes, cutoff_hz: float = 300.0) -> bytes:
    """First-order high-pass of a PCM WAV (other → melody_a when vocals silent)."""
    from scipy import signal

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.getnframes()
        raw = wf.readframes(frames)
    if sw != 2 or frames <= 0 or rate <= 0:
        return wav_bytes
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32).reshape(-1, nch)
    b, a = signal.butter(1, cutoff_hz, btype="highpass", fs=float(rate))
    out = signal.lfilter(b, a, samples, axis=0).astype(np.float32)
    peak = float(np.max(np.abs(out))) or 1.0
    if peak > 30000:
        out = out * (30000.0 / peak)
    pcm = out.astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(nch)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def map_stems_to_layers(
    stems: dict[str, bytes],
    *,
    vocals_silence_rms: float = VOCALS_SILENCE_RMS,
) -> tuple[dict[str, bytes], dict[str, str]]:
    """
    Map Demucs stems to base layers.

    Returns (layer_id → wav_bytes, mapping notes).
    """
    mapping: dict[str, str] = {
        "rhythm": "drums",
        "pad": "bass",
        "harmony": "other",
        "melody_a": "vocals",
    }
    layers: dict[str, bytes] = {
        "rhythm": stems["drums"],
        "pad": stems["bass"],
        "harmony": stems["other"],
        "melody_a": stems["vocals"],
    }
    vocals_rms = _wav_rms(stems["vocals"])
    if vocals_rms < vocals_silence_rms:
        layers["melody_a"] = _highpass_wav(stems["other"])
        mapping["melody_a"] = "other_highpass (vocals near-silent)"
        logger.info(
            "Vocals RMS %.2e below threshold; using high-passed other for melody_a",
            vocals_rms,
        )
    return layers, mapping


def write_separation_meta(path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def separate_and_install_stems(
    song_dir: Path,
    *,
    client: DemucsClient,
    model: str = "htdemucs",
    force: bool = False,
) -> list[Path]:
    """
    Separate the song seed mix into base layers and update the manifest.

    Returns written layer paths. Raises RuntimeError / OSError on failure.
    Skips when needs_separation is false (unless force).
    """
    song_dir = Path(song_dir)
    if not needs_separation(song_dir, force=force):
        logger.info("Skipping separation for %s (already separated or custom stems)", song_dir)
        return []

    manifest = load_manifest(song_dir)
    if manifest is None:
        raise FileNotFoundError(f"No manifest in {song_dir}")
    seed = _seed_source_for_layers(song_dir, manifest)
    if seed is None:
        raise FileNotFoundError(f"No seed audio in {song_dir}")

    audio_bytes = seed.read_bytes()
    result = client.separate(audio_bytes, filename=seed.name, model=model)
    layer_wavs, mapping = map_stems_to_layers(result.stems)

    written: list[Path] = []
    for layer_id in BASE_LAYER_IDS:
        wav = layer_wavs[layer_id]
        layer_dir = song_dir / layer_id
        layer_dir.mkdir(parents=True, exist_ok=True)
        # Remove stub copies with other extensions so mixer doesn't pick the old mp3.
        for stale in layer_dir.glob(f"{layer_id}_*"):
            if stale.is_file():
                stale.unlink()
        dest = layer_dir / f"{layer_id}_01.wav"
        dest.write_bytes(wav)
        written.append(dest)
        rel = f"{layer_id}/{dest.name}"
        manifest.layers[layer_id] = LayerEntry(
            src=rel,
            role="base",
            generated=False,
            baseGain=0.75,
        )

    manifest.playback_mode = "layered"
    save_manifest(song_dir, manifest)

    meta = {
        "model": result.model,
        "seed": str(seed.relative_to(song_dir)) if seed.is_relative_to(song_dir) else seed.name,
        "seedSha256": file_sha256(seed),
        "durationSeconds": result.duration_seconds,
        "mapping": mapping,
        "separatedAt": datetime.now(timezone.utc).isoformat(),
        "layers": {lid: f"{lid}/{lid}_01.wav" for lid in BASE_LAYER_IDS},
    }
    write_separation_meta(song_dir / SEPARATION_META_NAME, meta)
    logger.info("Separated stems for %s → %s", song_dir.name, [p.name for p in written])
    return written

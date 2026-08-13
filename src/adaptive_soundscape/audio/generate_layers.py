"""Offline orchestration: prompt → MusicGen API → validate → write stems."""

from __future__ import annotations

import logging
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from adaptive_soundscape.audio.music_manifest import LayerEntry, load_manifest, save_manifest
from adaptive_soundscape.audio.musicgen_client import MusicGenClient, write_generation_meta
from adaptive_soundscape.audio.prompt_builder import build_layer_prompt, scenario_bpm

logger = logging.getLogger(__name__)


class LayerValidationError(ValueError):
    pass


def validate_wav_bytes(
    wav_bytes: bytes,
    *,
    expected_seconds: float,
    tolerance: float = 0.05,
    max_peak: float = 0.99,
) -> tuple[float, float]:
    """Return (duration, peak). Raise if duration/peak unacceptable."""
    import io

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        rate = wf.getframerate()
        frames = wf.getnframes()
        sampwidth = wf.getsampwidth()
        nch = wf.getnchannels()
        raw = wf.readframes(frames)
    if rate <= 0 or frames <= 0:
        raise LayerValidationError("empty or invalid WAV")
    duration = frames / float(rate)
    rel_err = abs(duration - expected_seconds) / max(expected_seconds, 1e-3)
    if rel_err > tolerance:
        raise LayerValidationError(
            f"duration {duration:.3f}s not within {tolerance:.0%} of "
            f"{expected_seconds:.3f}s"
        )
    if sampwidth == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
    if nch > 1:
        samples = samples.reshape(-1, nch).mean(axis=1)
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    if peak >= max_peak:
        raise LayerValidationError(f"peak {peak:.3f} too hot (max {max_peak})")
    if peak < 1e-4:
        raise LayerValidationError("audio is near-silent")
    return duration, peak


def sync_song_tempo(song_dir: Path, scenario: str) -> float:
    """Write the scenario BPM onto the manifest; keep existing loop_seconds."""
    manifest = load_manifest(song_dir)
    if manifest is None:
        raise FileNotFoundError(f"No manifest in {song_dir}")
    bpm = scenario_bpm(scenario)
    if abs(float(manifest.bpm) - bpm) > 0.05:
        manifest.bpm = bpm
        save_manifest(song_dir, manifest)
        logger.info("Synced %s/%s bpm → %.1f", scenario, song_dir.name, bpm)
    return float(manifest.bpm)


def generate_and_install_layer(
    song_dir: Path,
    *,
    scenario: str,
    layer_id: str,
    client: MusicGenClient,
    model_size: str = "small",
    seed: int = 0,
) -> Path:
    bpm = sync_song_tempo(song_dir, scenario)
    manifest = load_manifest(song_dir)
    if manifest is None:
        raise FileNotFoundError(f"No manifest in {song_dir}")
    built = build_layer_prompt(
        scenario=scenario,
        layer_id=layer_id,
        bpm=bpm,
        loop_seconds=manifest.loop_seconds,
        bars_per_loop=manifest.bars_per_loop,
    )
    result = client.generate_layer(
        prompt=built.prompt,
        negative_prompt=built.negative_prompt,
        duration_seconds=manifest.loop_seconds,
        bpm=bpm,
        seed=seed,
        model_size=model_size,
    )
    duration, peak = validate_wav_bytes(
        result.wav_bytes, expected_seconds=manifest.loop_seconds
    )
    layer_dir = song_dir / layer_id
    layer_dir.mkdir(parents=True, exist_ok=True)
    dest = layer_dir / f"{layer_id}_ai_01.wav"
    dest.write_bytes(result.wav_bytes)
    rel = f"{layer_id}/{dest.name}"
    manifest.layers[layer_id] = LayerEntry(
        src=rel,
        role="intensity",
        generated=True,
        baseGain=0.75,
    )
    manifest.playback_mode = "layered"
    save_manifest(song_dir, manifest)
    write_generation_meta(
        layer_dir / "generation_meta.json",
        {
            "layerId": layer_id,
            "scenario": scenario,
            "songId": manifest.song_id,
            "prompt": result.prompt,
            "negativePrompt": built.negative_prompt,
            "seed": result.seed,
            "model": result.model,
            "durationSeconds": duration,
            "peak": peak,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
    )
    logger.info("Installed generated layer %s → %s", layer_id, dest)
    return dest

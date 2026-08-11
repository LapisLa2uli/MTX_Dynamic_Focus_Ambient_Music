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
# Absolute floor: truly empty vocals stem.
VOCALS_SILENCE_RMS = 1e-3
# Relative: Demucs often leaves quiet vocal bleed on instrumental tracks.
# If vocals are weaker than this fraction of ``other``, treat as instrumental.
VOCALS_OTHER_RATIO = 0.35
# Complementary split of Demucs ``other`` into lead vs chord bed.
OTHER_CROSSOVER_HZ = 320.0
OTHER_FILTER_ORDER = 4
HARMONY_BED_GAIN = 0.85
# Mid/lead bands for quality checks after the complementary split.
_MELODY_BAND_HZ = (350.0, 2500.0)
_MELODY_LEAD_HZ = (700.0, 4000.0)
_HARMONY_BODY_HZ = (40.0, 280.0)

# Back-compat aliases used by older call sites / tests.
HARMONY_LOWPASS_HZ = OTHER_CROSSOVER_HZ
HARMONY_FILTER_ORDER = OTHER_FILTER_ORDER


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


def _decode_wav(wav_bytes: bytes) -> tuple[np.ndarray, int, int, int]:
    """Return (float32 samples shaped [n, ch], rate, nch, sampwidth)."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.getnframes()
        raw = wf.readframes(frames)
    if frames <= 0 or rate <= 0:
        return np.zeros((0, max(nch, 1)), dtype=np.float32), rate, nch, sw
    if sw == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32).reshape(-1, nch)
        samples = samples / 32768.0
    elif sw == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32).reshape(-1, nch)
        samples = samples / 2147483648.0
    else:
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float32).reshape(-1, nch)
        samples = samples / 128.0 - 1.0
    return samples, rate, nch, sw


def _encode_wav(samples: np.ndarray, rate: int, nch: int) -> bytes:
    peak = float(np.max(np.abs(samples))) or 1.0
    if peak > 0.99:
        samples = samples * (0.99 / peak)
    pcm = (samples * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(nch)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _filter_wav(
    wav_bytes: bytes,
    *,
    cutoff_hz: float,
    btype: str,
    order: int = 1,
) -> bytes:
    """Butterworth filter of a PCM WAV."""
    from scipy import signal

    samples, rate, nch, sw = _decode_wav(wav_bytes)
    if samples.size == 0 or rate <= 0 or sw not in {2, 4}:
        return wav_bytes
    nyquist = float(rate) * 0.5
    cutoff = max(20.0, min(float(cutoff_hz), nyquist * 0.95))
    b, a = signal.butter(max(1, int(order)), cutoff, btype=btype, fs=float(rate))
    out = signal.lfilter(b, a, samples, axis=0).astype(np.float32)
    return _encode_wav(out, rate, nch)


def _highpass_wav(
    wav_bytes: bytes,
    cutoff_hz: float = OTHER_CROSSOVER_HZ,
    *,
    order: int = OTHER_FILTER_ORDER,
) -> bytes:
    return _filter_wav(
        wav_bytes, cutoff_hz=cutoff_hz, btype="highpass", order=order
    )


def _lowpass_wav(
    wav_bytes: bytes,
    cutoff_hz: float = OTHER_CROSSOVER_HZ,
    *,
    order: int = OTHER_FILTER_ORDER,
) -> bytes:
    return _filter_wav(
        wav_bytes, cutoff_hz=cutoff_hz, btype="lowpass", order=order
    )


def _band_rms(wav_bytes: bytes, lo_hz: float, hi_hz: float) -> float:
    from scipy import signal

    samples, rate, nch, _sw = _decode_wav(wav_bytes)
    if samples.size == 0 or rate <= 0:
        return 0.0
    mono = samples.mean(axis=1) if nch > 1 else samples.reshape(-1)
    nyquist = float(rate) * 0.5
    lo = max(20.0, min(lo_hz, nyquist * 0.9))
    hi = max(lo + 1.0, min(hi_hz, nyquist * 0.98))
    b, a = signal.butter(2, [lo / nyquist, hi / nyquist], btype="band")
    filtered = signal.lfilter(b, a, mono)
    return float(np.sqrt(np.mean(filtered * filtered)))


def _scale_wav(wav_bytes: bytes, gain: float) -> bytes:
    samples, rate, nch, _sw = _decode_wav(wav_bytes)
    if samples.size == 0:
        return wav_bytes
    return _encode_wav(samples * float(gain), rate, nch)


def _sum_wavs(a: bytes, b: bytes) -> bytes:
    sa, rate, nch, _ = _decode_wav(a)
    sb, rate_b, nch_b, _ = _decode_wav(b)
    if sa.size == 0:
        return b
    if sb.size == 0:
        return a
    if rate != rate_b or nch != nch_b:
        return a
    n = min(sa.shape[0], sb.shape[0])
    return _encode_wav(sa[:n] + sb[:n], rate, nch)


def _split_other_to_melody_harmony(
    other_wav: bytes,
    *,
    crossover_hz: float = OTHER_CROSSOVER_HZ,
    order: int = OTHER_FILTER_ORDER,
    harmony_gain: float = HARMONY_BED_GAIN,
) -> tuple[bytes, bytes]:
    """
    Complementary split of Demucs ``other``.

    High-pass → melody_a (lead / motif).
    Low-pass → harmony (chord / body), so the lead layer does not keep the pad bed.
    """
    melody = _highpass_wav(other_wav, crossover_hz, order=order)
    harmony = _scale_wav(
        _lowpass_wav(other_wav, crossover_hz, order=order), harmony_gain
    )
    return melody, harmony


def _melody_retains_harmony_body(melody_wav: bytes) -> bool:
    """True when melody_a still holds the warm chord body (unsplit ``other``)."""
    lo, hi = _HARMONY_BODY_HZ
    mid_lo, mid_hi = _MELODY_BAND_HZ
    body = _band_rms(melody_wav, lo, hi)
    mid = _band_rms(melody_wav, mid_lo, mid_hi)
    if mid < VOCALS_SILENCE_RMS:
        return False
    return body > mid * 0.55


def _pick_other_source(melody_wav: bytes, harmony_wav: bytes) -> bytes:
    """Recover Demucs ``other`` (or the closest installed stand-in) for re-split."""
    if _melody_retains_harmony_body(melody_wav):
        return melody_wav
    lo, hi = _MELODY_BAND_HZ
    mel_mid = _band_rms(melody_wav, lo, hi)
    har_mid = _band_rms(harmony_wav, lo, hi)
    if har_mid > mel_mid * 1.15:
        # Pre-repair state: lead still sits in harmony.
        return harmony_wav
    # Already crossover-split: approximate original ``other`` by summing.
    gain = HARMONY_BED_GAIN if HARMONY_BED_GAIN > 1e-6 else 1.0
    return _sum_wavs(melody_wav, _scale_wav(harmony_wav, 1.0 / gain))


def _harmony_leaks_melody(melody_wav: bytes, harmony_wav: bytes) -> bool:
    """True when harmony still carries recognizable lead (above crossover)."""
    lo, hi = _MELODY_LEAD_HZ
    mel_lead = _band_rms(melody_wav, lo, hi)
    har_lead = _band_rms(harmony_wav, lo, hi)
    if mel_lead < VOCALS_SILENCE_RMS:
        return False
    return har_lead > mel_lead * 0.20


def _is_instrumental_mix(
    vocals_rms: float,
    other_rms: float,
    *,
    vocals_silence_rms: float = VOCALS_SILENCE_RMS,
    vocals_other_ratio: float = VOCALS_OTHER_RATIO,
) -> bool:
    """True when Demucs vocals are silence or quiet bleed vs the melodic ``other`` stem."""
    if vocals_rms < vocals_silence_rms:
        return True
    if other_rms <= vocals_silence_rms:
        return False
    return (vocals_rms / other_rms) < vocals_other_ratio


def map_stems_to_layers(
    stems: dict[str, bytes],
    *,
    vocals_silence_rms: float = VOCALS_SILENCE_RMS,
    vocals_other_ratio: float = VOCALS_OTHER_RATIO,
    harmony_lowpass_hz: float = OTHER_CROSSOVER_HZ,
) -> tuple[dict[str, bytes], dict[str, str]]:
    """
    Map Demucs stems to base layers.

    Focus / soundtrack mixes are usually instrumental: Demucs puts the lead in
    ``other`` and leaves a near-empty ``vocals`` bleed. ``other`` is then split
    with a complementary crossover into melody_a (high-pass) and harmony
    (low-pass bed). When vocals are clearly present they remain the melody layer.
    """
    mapping: dict[str, str] = {
        "rhythm": "drums",
        "pad": "bass",
    }
    layers: dict[str, bytes] = {
        "rhythm": stems["drums"],
        "pad": stems["bass"],
    }
    vocals_rms = _wav_rms(stems["vocals"])
    other_rms = _wav_rms(stems["other"])
    if _is_instrumental_mix(
        vocals_rms,
        other_rms,
        vocals_silence_rms=vocals_silence_rms,
        vocals_other_ratio=vocals_other_ratio,
    ):
        melody, harmony = _split_other_to_melody_harmony(
            stems["other"], crossover_hz=harmony_lowpass_hz
        )
        layers["melody_a"] = melody
        layers["harmony"] = harmony
        mapping["melody_a"] = (
            f"other_highpass_{int(harmony_lowpass_hz)}hz (instrumental)"
        )
        mapping["harmony"] = (
            f"other_lowpass_{int(harmony_lowpass_hz)}hz_x{HARMONY_BED_GAIN:g} "
            "(instrumental)"
        )
        logger.info(
            "Instrumental mix (vocals RMS %.2e vs other %.2e); "
            "split other @ %.0f Hz → melody_a/harmony",
            vocals_rms,
            other_rms,
            harmony_lowpass_hz,
        )
    else:
        layers["melody_a"] = stems["vocals"]
        layers["harmony"] = stems["other"]
        mapping["melody_a"] = "vocals"
        mapping["harmony"] = "other"
    mapping["vocals_rms"] = f"{vocals_rms:.6f}"
    mapping["other_rms"] = f"{other_rms:.6f}"
    return layers, mapping


def layers_look_melody_swapped(
    song_dir: Path,
    *,
    vocals_other_ratio: float = VOCALS_OTHER_RATIO,
    vocals_silence_rms: float = VOCALS_SILENCE_RMS,
) -> bool:
    """True when installed melody/harmony assignment still needs fixing."""
    del vocals_other_ratio  # used only for meta-based legacy path below
    melody_path = _layer_file(song_dir, "melody_a")
    harmony_path = _layer_file(song_dir, "harmony")
    if melody_path is None or harmony_path is None:
        return False
    if melody_path.suffix.lower() != ".wav" or harmony_path.suffix.lower() != ".wav":
        return False
    melody_wav = melody_path.read_bytes()
    harmony_wav = harmony_path.read_bytes()
    melody_rms = _wav_rms(melody_wav)
    harmony_rms = _wav_rms(harmony_wav)

    if _harmony_leaks_melody(melody_wav, harmony_wav):
        return True
    if _melody_retains_harmony_body(melody_wav):
        return True

    # Legacy: quiet Demucs vocals → melody_a while lead stayed in harmony.
    meta_path = song_dir / SEPARATION_META_NAME
    if not meta_path.is_file() or harmony_rms <= vocals_silence_rms:
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    mel_src = str((meta.get("mapping") or {}).get("melody_a", ""))
    if mel_src != "vocals":
        return False
    return melody_rms < harmony_rms * 0.85


def repair_melody_harmony_layers(
    song_dir: Path,
    *,
    force: bool = False,
    harmony_lowpass_hz: float = OTHER_CROSSOVER_HZ,
) -> list[Path]:
    """
    Fix already-separated songs where melody/harmony still share content.

    Uses the installed WAVs (no Demucs): recover ``other``, then complementary
    crossover-split into melody_a / harmony. Returns rewritten paths, or [].
    """
    song_dir = Path(song_dir)
    melody_path = _layer_file(song_dir, "melody_a")
    harmony_path = _layer_file(song_dir, "harmony")
    if melody_path is None or harmony_path is None:
        raise FileNotFoundError(f"Missing melody_a/harmony in {song_dir}")

    melody_wav = melody_path.read_bytes()
    harmony_wav = harmony_path.read_bytes()
    needs = force or layers_look_melody_swapped(song_dir)
    if not needs:
        return []

    other = _pick_other_source(melody_wav, harmony_wav)
    melody_bytes, harmony_bytes = _split_other_to_melody_harmony(
        other, crossover_hz=harmony_lowpass_hz
    )

    written: list[Path] = []
    payloads = {
        "melody_a": melody_bytes,
        "harmony": harmony_bytes,
    }
    manifest = load_manifest(song_dir)
    for layer_id, payload in payloads.items():
        layer_dir = song_dir / layer_id
        layer_dir.mkdir(parents=True, exist_ok=True)
        for stale in layer_dir.glob(f"{layer_id}_*"):
            if stale.is_file():
                stale.unlink()
        dest = layer_dir / f"{layer_id}_01.wav"
        dest.write_bytes(payload)
        written.append(dest)
        if manifest is not None:
            manifest.layers[layer_id] = LayerEntry(
                src=f"{layer_id}/{dest.name}",
                role="base",
                generated=False,
                baseGain=0.75,
            )
    if manifest is not None:
        save_manifest(song_dir, manifest)

    meta_path = song_dir / SEPARATION_META_NAME
    meta: dict = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
    mapping = dict(meta.get("mapping") or {})
    mapping["melody_a"] = (
        f"other_highpass_{int(harmony_lowpass_hz)}hz (instrumental repair)"
    )
    mapping["harmony"] = (
        f"other_lowpass_{int(harmony_lowpass_hz)}hz_x{HARMONY_BED_GAIN:g} "
        "(instrumental repair)"
    )
    mapping["repairedAt"] = datetime.now(timezone.utc).isoformat()
    meta["mapping"] = mapping
    write_separation_meta(meta_path, meta)
    logger.info("Repaired melody/harmony assignment for %s", song_dir.name)
    return written


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

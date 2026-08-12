"""Phrase-boundary detection for adaptive song switching.

Precompute per-track 0.2 s tick features (per-tick RMS volume and median pyin
pitch) into ``features.json`` inside each song directory.  At runtime the
:class:`PhraseBoundaryDetector` loads the cached ticks and actively evaluates
the 3 s window ``(t, t+3]`` on every 0.2 s tick (sliding-window update after the
first tick).  The first window whose phrase-end probability exceeds the
threshold marks a sentence end located at the end of that window.

The precompute path needs ``librosa`` (imported lazily, heavy); the runtime
detector is pure numpy + json and works inside the app process without extra
dependencies.

Constants follow the Schubert Winterreise logistic regression fit:

    p = 1 / (1 + exp(-(b0 + b_vol * z_vol + b_pitch * z_pitch)))
    b0 = -1.058, b_vol = -0.425, b_pitch = +0.290

z_vol / z_pitch are per-song z-scores (mean/std of all full 3 s windows) of the
window's volume sum and |median-f0 change| sum.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

TICK_SECONDS = 0.2
WINDOW_SECONDS = 3.0
N_TICKS = int(round(WINDOW_SECONDS / TICK_SECONDS))  # 15 ticks per window
SAMPLE_RATE = 22050
TICK_HOP = int(round(TICK_SECONDS * SAMPLE_RATE))  # 4410 samples per tick
PITCH_MIN = 60.0
PITCH_MAX = 2000.0
PYIN_FRAME = 4096
PYIN_HOP = PYIN_FRAME // 4  # pyin default hop_length

# Trained logistic constants (user-provided).
B0 = -1.058
B_VOL = -0.425
B_PITCH = 0.290

FEATURES_FILE = "features.json"
AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aiff", ".aif", ".aac"}

EPS = 1e-12


def sigmoid(z_vol: float, z_pitch: float) -> float:
    """Phrase-end probability from z-scored volume / pitch-change features."""
    z = B0 + B_VOL * z_vol + B_PITCH * z_pitch
    return 1.0 / (1.0 + math.exp(-z))


# ---------------------------------------------------------------------------
# Precompute (needs librosa)
# ---------------------------------------------------------------------------
def _audio_files(song_dir: Path) -> list[Path]:
    files: list[Path] = []
    for p in sorted(song_dir.rglob("*")):
        if (
            p.is_file()
            and p.suffix.lower() in AUDIO_EXTENSIONS
            and p.name != FEATURES_FILE
        ):
            files.append(p)
    return files


def _tick_features(audio_path: Path) -> dict[str, Any] | None:
    """Per-tick volume + pitch sequences for one audio file.

    Mirrors ``swd_sample_features.feature_vec``: 0.2 s ticks, RMS volume per
    tick, median pyin pitch per tick, and per-song z-score statistics computed
    over every full 3 s window aligned to the tick grid.
    """
    import librosa  # lazy: only used during precompute

    y, sr = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True)
    if y is None or len(y) < TICK_HOP * N_TICKS:
        return None
    n_ticks = len(y) // TICK_HOP

    # Per-tick RMS volume.
    seg = y[: n_ticks * TICK_HOP].reshape(n_ticks, TICK_HOP)
    volume_tick = np.sqrt(np.mean(seg.astype(np.float64) ** 2, axis=1) + EPS)

    # Per-tick median pyin pitch (frame_length=4096, hop=1024).
    f0, _, _ = librosa.pyin(
        y, fmin=PITCH_MIN, fmax=PITCH_MAX, sr=sr, frame_length=PYIN_FRAME
    )
    f0_tick = np.full(n_ticks, np.nan, dtype=np.float64)
    for k in range(n_ticks):
        j0 = (k * TICK_HOP) // PYIN_HOP
        j1 = ((k + 1) * TICK_HOP) // PYIN_HOP
        chunk = f0[j0:j1]
        v = chunk[~np.isnan(chunk)]
        if len(v):
            f0_tick[k] = float(np.median(v))

    # z-score statistics over every full 3 s window aligned to the tick grid.
    vol_sums: list[float] = []
    pitch_sums: list[float] = []
    for i in range(n_ticks - N_TICKS + 1):
        vol_sums.append(float(volume_tick[i : i + N_TICKS].sum()))
        wf = f0_tick[i : i + N_TICKS]
        valid = wf[~np.isnan(wf)]
        ps = 0.0
        if len(valid) >= 2:
            ps = float(np.sum(np.abs(np.diff(valid))))
        pitch_sums.append(ps)
    vol_mean = float(np.mean(vol_sums)) if vol_sums else 0.0
    vol_std = float(np.std(vol_sums, ddof=1)) if len(vol_sums) > 1 else 0.0
    pitch_mean = float(np.mean(pitch_sums)) if pitch_sums else 0.0
    pitch_std = float(np.std(pitch_sums, ddof=1)) if len(pitch_sums) > 1 else 0.0
    if vol_std < EPS:
        vol_std = EPS
    if pitch_std < EPS:
        pitch_std = EPS

    return {
        "duration": round(n_ticks * TICK_SECONDS, 3),
        "volume_tick": [float(v) for v in volume_tick],
        "f0_tick": [float(v) for v in f0_tick],
        "vol_mean": vol_mean,
        "vol_std": vol_std,
        "pitch_mean": pitch_mean,
        "pitch_std": pitch_std,
        "windows": len(vol_sums),
    }


def precompute_song_features(song_dir: Path) -> Path | None:
    """Compute feature ticks for every audio file under ``song_dir`` and store
    them in ``<song_dir>/features.json``.

    Returns the written file, or ``None`` if there is nothing to compute
    (no audio files / librosa unavailable / all files too short).
    """
    song_dir = Path(song_dir)
    files = _audio_files(song_dir)
    if not files:
        return None
    tracks: dict[str, dict[str, Any]] = {}
    for p in files:
        try:
            feat = _tick_features(p)
        except ImportError:
            logger.warning(
                "phrase_boundary: librosa unavailable, cannot precompute %s", p
            )
            return None
        except Exception:
            logger.exception("phrase_boundary: failed to precompute %s", p)
            continue
        if feat is not None:
            tracks[p.relative_to(song_dir).as_posix()] = feat
    if not tracks:
        return None
    data = {
        "tick_seconds": TICK_SECONDS,
        "window_seconds": WINDOW_SECONDS,
        "sample_rate": SAMPLE_RATE,
        "constants": {"b0": B0, "b_vol": B_VOL, "b_pitch": B_PITCH},
        "tracks": tracks,
    }
    out = song_dir / FEATURES_FILE
    tmp = out.with_name(out.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, allow_nan=True)
    tmp.replace(out)
    logger.info("phrase_boundary: wrote %s (%d tracks)", out, len(tracks))
    return out


# ---------------------------------------------------------------------------
# Runtime detection (pure numpy + json)
# ---------------------------------------------------------------------------
class PhraseBoundaryDetector:
    """Load cached feature ticks and actively detect sentence ends ahead of the
    current playback position."""

    def __init__(
        self,
        assets_dir: Path,
        *,
        threshold: float = 0.5,
        search_seconds: float = 10.0,
    ) -> None:
        self.assets_dir = Path(assets_dir)
        self.threshold = float(threshold)
        self.search_seconds = float(search_seconds)
        self._cache: dict[Path, dict[str, Any]] = {}

    def _load(self, song_dir: Path) -> dict[str, Any] | None:
        feat_path = song_dir / FEATURES_FILE
        if feat_path in self._cache:
            return self._cache[feat_path]
        if not feat_path.is_file():
            return None
        try:
            with feat_path.open(encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            logger.exception("phrase_boundary: failed to load %s", feat_path)
            return None
        self._cache[feat_path] = data
        return data

    @staticmethod
    def _song_dir_for(track_path: Path) -> Path | None:
        """Nearest ancestor directory that contains a features.json."""
        p = Path(track_path).resolve()
        for parent in (p.parent, *p.parents):
            if (parent / FEATURES_FILE).is_file():
                return parent
        return None

    @staticmethod
    def _entry(data: dict[str, Any], rel: str) -> dict[str, Any] | None:
        tracks = data.get("tracks") or {}
        if rel in tracks:
            return tracks[rel]
        # Fall back to the longest precomputed track of the song.
        best: dict[str, Any] | None = None
        for e in tracks.values():
            if best is None or (e.get("duration") or 0) > (best.get("duration") or 0):
                best = e
        return best

    def search_boundary(
        self, track_path: Path, position_sec: float
    ) -> float | None:
        """Return the end time of the first detected sentence end, else ``None``.

        The window (t, t+3] is evaluated actively on every 0.2 s tick.  After
        the first tick the window aggregates are updated incrementally instead
        of being recomputed (``val = val - parameter_t + parameter_{t+3}``).
        The first window whose phrase-end probability exceeds the threshold
        marks a sentence end located at the end of that window.  Only the next
        ``search_seconds`` of detections (default 10 s = 50 ticks) are
        considered.
        """
        if position_sec < 0:
            return None
        song_dir = self._song_dir_for(track_path)
        if song_dir is None:
            return None
        data = self._load(song_dir)
        if data is None:
            return None
        try:
            rel = Path(track_path).resolve().relative_to(song_dir).as_posix()
        except ValueError:
            rel = track_path.name
        entry = self._entry(data, rel)
        if entry is None:
            return None

        volume_tick = entry.get("volume_tick") or []
        f0_tick = entry.get("f0_tick") or []
        n = len(volume_tick)
        if n < N_TICKS:
            return None
        tick = float(data.get("tick_seconds") or TICK_SECONDS)
        vol_mean = float(entry.get("vol_mean") or 0.0)
        vol_std = float(entry.get("vol_std") or EPS)
        pitch_mean = float(entry.get("pitch_mean") or 0.0)
        pitch_std = float(entry.get("pitch_std") or EPS)

        f0_arr = np.asarray(f0_tick, dtype=np.float64)
        vol_arr = np.asarray(volume_tick, dtype=np.float64)

        # Detection budget: one (t, t+3] evaluation per tick (10 s = 50 ticks).
        max_detections = max(int(round(self.search_seconds / tick)), 1)
        i0 = max(int(math.ceil((position_sec + 1e-6) / tick)), 0)
        i_max = min(i0 + max_detections - 1, n - N_TICKS)
        if i_max < i0:
            return None

        # Sliding-window aggregates for the (t, t+3] window.  Volume is a
        # plain running sum; pitch is NaN-aware, so per-tick change deltas
        # (pc[k] = |f0[k] - f0[last valid before k]|) are precomputed once and
        # windowed via cumulative sums -- every tick after the first is then
        # just val = val - parameter_t + parameter_{t+3}.
        valid_mask = ~np.isnan(f0_arr)
        pc = np.zeros(n, dtype=np.float64)
        valid_idx = np.flatnonzero(valid_mask)
        if valid_idx.size:
            slot = np.searchsorted(valid_idx, valid_idx) - 1
            has_prev = slot >= 0
            cur = valid_idx[has_prev]
            prev_v = valid_idx[slot[has_prev]]
            pc[cur] = np.abs(f0_arr[cur] - f0_arr[prev_v])
        pc_cum = np.concatenate(([0.0], np.cumsum(pc)))
        vol_cum = np.concatenate(([0.0], np.cumsum(vol_arr)))

        # first_valid[i] = first valid tick index >= i (sentinel n if none).
        first_valid = np.full(n + 1, n, dtype=np.int64)
        if valid_idx.size:
            boundary = np.searchsorted(valid_idx, np.arange(n + 1), side="left")
            first_valid = np.where(
                boundary < valid_idx.size,
                valid_idx[np.minimum(boundary, valid_idx.size - 1)],
                n,
            )

        for i in range(i0, i_max + 1):
            vol_sum = float(vol_cum[i + N_TICKS] - vol_cum[i])
            # Pitch-change sum inside (i, i+N): windowed pc deltas minus the
            # first valid tick's own delta, which points outside the window.
            mid = pc_cum[i + N_TICKS] - pc_cum[i + 1]
            j = int(first_valid[i])
            if i < j < i + N_TICKS:
                mid -= pc[j]
            z_vol = (vol_sum - vol_mean) / vol_std
            z_pitch = (max(mid, 0.0) - pitch_mean) / pitch_std
            if sigmoid(z_vol, z_pitch) > self.threshold:
                return float((i + N_TICKS) * tick)
        return None

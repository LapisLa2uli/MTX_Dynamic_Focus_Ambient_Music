"""Smoke test for phrase_boundary (created/removed during development)."""

from __future__ import annotations

import sys
import time
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import soundfile as sf

from adaptive_soundscape.audio.phrase_boundary import (
    PhraseBoundaryDetector,
    _tick_features,
    precompute_song_features,
)

sr = 22050
N = 30
t = np.arange(sr * N) / sr
# Loud steady music for [0,24s) and [26.5s,30s); a quiet 2.5 s phrase ending
# with strong vibrato in [24s,26.5s). Trained model: quiet + pitch change → end.
amp = np.where((t >= 24.0) & (t < 26.5), 0.02, 0.8) * (1.0 + 0.15 * np.sin(2 * np.pi * 0.4 * t))
f0 = np.where((t >= 24.0) & (t < 26.5), 120.0 + 9.0 * np.sin(2 * np.pi * 5.0 * t), 120.0)
sig = amp * np.sin(2 * np.pi * np.cumsum(f0) / sr)

with tempfile.TemporaryDirectory() as d:
    song = Path(d) / "song"
    (song / "focus").mkdir(parents=True)
    audio = song / "focus" / "focus_01.wav"
    sf.write(audio, sig, sr)
    _tick_features(audio)  # warm librosa import
    t0 = time.perf_counter()
    feat = _tick_features(audio)
    dt = time.perf_counter() - t0
    print(f"_tick_features (30s, warm): {dt:.2f}s -> {dt / N * 60:.1f}s per minute of audio")
    out = precompute_song_features(song)
    print("precompute_song_features ->", out)
    det = PhraseBoundaryDetector(d, threshold=0.3, search_seconds=10.0)
    for pos in (0.2, 18.0, 20.0):
        b = det.search_boundary(audio, position_sec=pos)
        print(f"search_boundary({pos}s) -> {b}")
    print("SMOKE OK")

"""Demucs wrapper (htdemucs) for local stem separation."""

from __future__ import annotations

import io
import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

STEM_NAMES = ("drums", "bass", "other", "vocals")
DEFAULT_MODEL = "htdemucs"
SUPPORTED_MODELS = ("htdemucs", "htdemucs_ft", "mdx_extra")


def _resolve_torch_device() -> str:
    """Prefer CUDA; honor DEMUCS_DEVICE=cuda|cpu|auto."""
    import torch

    requested = os.environ.get("DEMUCS_DEVICE", "auto").strip().lower() or "auto"
    cuda_ok = bool(torch.cuda.is_available())
    if requested in {"cuda", "gpu"}:
        if not cuda_ok:
            raise RuntimeError(
                "DEMUCS_DEVICE=cuda but CUDA is unavailable. "
                f"torch={getattr(torch, '__version__', '?')} at "
                f"{getattr(torch, '__file__', '?')}. "
                "Install a CUDA wheel into the conda env and start with "
                "PYTHONNOUSERSITE=1 so a CPU torch from user site-packages "
                "cannot shadow it."
            )
        return "cuda"
    if requested == "cpu":
        return "cpu"
    return "cuda" if cuda_ok else "cpu"


class DemucsEngine:
    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model if model in SUPPORTED_MODELS else DEFAULT_MODEL
        self.device = "cpu"
        self._separator = None
        self.stub_mode = os.environ.get("DEMUCS_STUB", "").lower() in {
            "1",
            "true",
            "yes",
        }

    @property
    def loaded(self) -> bool:
        return self.stub_mode or self._separator is not None

    def load(self) -> None:
        if self.stub_mode:
            logger.warning("DEMUCS_STUB=1 — returning synthetic stems (no model)")
            return
        if self._separator is not None:
            return
        import torch
        from demucs.api import Separator

        self.device = _resolve_torch_device()
        logger.info(
            "Loading Demucs %s on %s (torch=%s) …",
            self.model,
            self.device,
            getattr(torch, "__version__", "?"),
        )
        if self.device.startswith("cuda"):
            logger.info("CUDA device: %s", torch.cuda.get_device_name(0))
        self._separator = Separator(
            model=self.model,
            device=self.device,
        )
        logger.info("Demucs ready on %s", self.device)

    def separate(
        self,
        audio_bytes: bytes,
        *,
        filename: str = "mix.wav",
    ) -> tuple[dict[str, bytes], float]:
        """Return ({stem_name: wav_bytes}, duration_seconds)."""
        if self.stub_mode:
            return _stub_stems(audio_bytes), _probe_duration(audio_bytes)

        if self._separator is None:
            self.load()

        suffix = Path(filename).suffix.lower() or ".wav"
        with tempfile.TemporaryDirectory(prefix="demucs_") as tmp:
            tmp_dir = Path(tmp)
            src = tmp_dir / f"input{suffix}"
            src.write_bytes(audio_bytes)
            origin, separated = self._separator.separate_audio_file(src)

        # separated: dict[str, Tensor] shape (channels, samples)
        sample_rate = int(getattr(self._separator, "samplerate", 44100))
        if hasattr(origin, "shape"):
            n_samples = int(origin.shape[-1])
        else:
            n_samples = 0
        duration = n_samples / float(sample_rate) if sample_rate and n_samples else 0.0

        stems: dict[str, bytes] = {}
        for name in STEM_NAMES:
            if name not in separated:
                raise RuntimeError(f"Demucs output missing stem '{name}'")
            tensor = separated[name]
            arr = tensor.detach().cpu().numpy()
            if arr.ndim == 1:
                samples = arr.astype(np.float32)
            else:
                # (channels, samples) → prefer stereo write; soundfile wants (samples, ch)
                samples = np.ascontiguousarray(arr.T.astype(np.float32))
            peak = float(np.max(np.abs(samples))) if samples.size else 0.0
            if peak > 0.99:
                samples = samples * (0.95 / peak)
            stems[name] = _float_to_wav_bytes(samples, sample_rate)
        return stems, duration


def _float_to_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _probe_duration(audio_bytes: bytes) -> float:
    try:
        import soundfile as sf

        with sf.SoundFile(io.BytesIO(audio_bytes)) as handle:
            if handle.samplerate <= 0:
                return 1.0
            return float(len(handle)) / float(handle.samplerate)
    except Exception:
        return 1.0


def _stub_stems(audio_bytes: bytes, rate: int = 44100) -> dict[str, bytes]:
    """Four distinct tones so layers are audibly different in wiring tests."""
    duration = max(_probe_duration(audio_bytes), 0.5)
    n = max(int(duration * rate), 1)
    t = np.arange(n, dtype=np.float32) / rate
    freqs = {
        "drums": 80.0,
        "bass": 110.0,
        "other": 220.0,
        "vocals": 330.0,
    }
    out: dict[str, bytes] = {}
    for name, freq in freqs.items():
        audio = 0.12 * np.sin(2 * np.pi * freq * t)
        if name == "drums":
            # Soft pulse envelope
            pulse = (np.sin(2 * np.pi * 2.0 * t) > 0).astype(np.float32)
            audio = audio * (0.3 + 0.7 * pulse)
        fade = min(rate // 20, n // 8)
        if fade > 1:
            env = np.ones(n, dtype=np.float32)
            env[:fade] = np.linspace(0, 1, fade, dtype=np.float32)
            env[-fade:] = np.linspace(1, 0, fade, dtype=np.float32)
            audio *= env
        out[name] = _float_to_wav_bytes(audio.astype(np.float32), rate)
    return out


@lru_cache(maxsize=2)
def get_engine(model: str = DEFAULT_MODEL) -> DemucsEngine:
    engine = DemucsEngine(model=model)
    engine.load()
    return engine

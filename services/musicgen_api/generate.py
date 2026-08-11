"""MusicGen wrapper (Meta facebook/musicgen-* via Hugging Face transformers)."""

from __future__ import annotations

import io
import logging
import os
from functools import lru_cache

import numpy as np

logger = logging.getLogger(__name__)

MODEL_IDS = {
    "small": "facebook/musicgen-small",
    "medium": "facebook/musicgen-medium",
}


class MusicGenEngine:
    def __init__(self, model_size: str = "small") -> None:
        self.model_size = model_size if model_size in MODEL_IDS else "small"
        self.model_id = MODEL_IDS[self.model_size]
        self.device = "cpu"
        self._model = None
        self._processor = None
        self.stub_mode = os.environ.get("MUSICGEN_STUB", "").lower() in {
            "1",
            "true",
            "yes",
        }

    @property
    def loaded(self) -> bool:
        return self.stub_mode or self._model is not None

    def load(self) -> None:
        if self.stub_mode:
            logger.warning("MUSICGEN_STUB=1 — returning synthetic audio (no model)")
            return
        if self._model is not None:
            return
        import torch
        from transformers import AutoProcessor, MusicgenForConditionalGeneration

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        model_src = os.environ.get("MUSICGEN_MODEL_PATH", self.model_id)
        logger.info("Loading %s on %s …", model_src, self.device)
        self._processor = AutoProcessor.from_pretrained(model_src)
        self._model = MusicgenForConditionalGeneration.from_pretrained(model_src)
        self._model.to(self.device)
        self._model.eval()
        logger.info("MusicGen ready")

    def generate(
        self,
        *,
        prompt: str,
        duration_seconds: float = 27.428,
        seed: int = 0,
    ) -> tuple[bytes, float]:
        """Return (wav_bytes, actual_duration)."""
        if self.stub_mode:
            return _stub_wav(duration_seconds, seed), duration_seconds
        if self._model is None or self._processor is None:
            self.load()
        import torch

        # MusicGen frame rate ≈ 50 Hz; tokens ≈ duration * 50
        max_new_tokens = max(int(duration_seconds * 50), 64)
        # transformers MusicGen rejects `generator=` in model_kwargs; seed via global RNG
        if seed:
            torch.manual_seed(int(seed))
            if self.device == "cuda":
                torch.cuda.manual_seed_all(int(seed))
        inputs = self._processor(
            text=[prompt],
            padding=True,
            return_tensors="pt",
        ).to(self.device)
        with torch.no_grad():
            audio_values = self._model.generate(
                **inputs,
                do_sample=True,
                guidance_scale=3.0,
                max_new_tokens=max_new_tokens,
            )
        # audio_values: (batch, channels, samples)
        audio = audio_values[0, 0].cpu().numpy().astype(np.float32)
        sr = int(getattr(self._model.config.audio_encoder, "sampling_rate", 32000))
        # Resample / trim to requested duration at 32k then write wav; client accepts any rate.
        target_len = int(duration_seconds * sr)
        if len(audio) > target_len:
            audio = audio[:target_len]
        elif len(audio) < target_len:
            audio = np.pad(audio, (0, target_len - len(audio)))
        peak = float(np.max(np.abs(audio))) or 1.0
        if peak > 0.95:
            audio = audio * (0.9 / peak)
        wav_bytes = _float_to_wav_bytes(audio, sr)
        return wav_bytes, len(audio) / float(sr)


def _float_to_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _stub_wav(duration_seconds: float, seed: int, rate: int = 32000) -> bytes:
    rng = np.random.default_rng(seed or 1)
    n = max(int(duration_seconds * rate), 1)
    t = np.arange(n, dtype=np.float32) / rate
    freq = 220.0 + (seed % 40)
    audio = 0.15 * np.sin(2 * np.pi * freq * t)
    audio += 0.05 * np.sin(2 * np.pi * (freq * 1.5) * t)
    audio += 0.01 * rng.standard_normal(n).astype(np.float32)
    # Short edge fades for loop friendliness
    fade = min(rate // 10, n // 8)
    if fade > 1:
        env = np.ones(n, dtype=np.float32)
        env[:fade] = np.linspace(0, 1, fade, dtype=np.float32)
        env[-fade:] = np.linspace(1, 0, fade, dtype=np.float32)
        audio *= env
    return _float_to_wav_bytes(audio.astype(np.float32), rate)


@lru_cache(maxsize=2)
def get_engine(model_size: str = "small") -> MusicGenEngine:
    engine = MusicGenEngine(model_size=model_size)
    engine.load()
    return engine

"""FastAPI sidecar for self-hosted Meta MusicGen (localhost only)."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from generate import MODEL_IDS, get_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("musicgen_api")

app = FastAPI(title="Adaptive Soundscape MusicGen API", version="0.1.0")

DEFAULT_MODEL = os.environ.get("MUSICGEN_MODEL_SIZE", "small")


class GenerateRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    duration_seconds: float = Field(default=27.428, ge=2.0, le=60.0)
    bpm: float = Field(default=70.0, ge=40.0, le=180.0)
    seed: int = 0
    model_size: str = "small"


@app.on_event("startup")
def _startup() -> None:
    # Eager-load default model (or stub).
    try:
        get_engine(DEFAULT_MODEL)
    except Exception:
        logger.exception("Failed to preload MusicGen; /health will report unloaded")


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        engine = get_engine(DEFAULT_MODEL)
        return {
            "ok": True,
            "loaded": engine.loaded,
            "stub": engine.stub_mode,
            "device": engine.device,
            "model": engine.model_id,
            "models": list(MODEL_IDS.keys()),
        }
    except Exception as exc:
        return {"ok": False, "loaded": False, "error": str(exc)}


@app.post("/v1/generate_layer")
def generate_layer(req: GenerateRequest) -> dict[str, Any]:
    # negative_prompt is absorbed into the text prompt for MusicGen (no native CFG neg).
    prompt = req.prompt
    if req.negative_prompt.strip():
        prompt = f"{prompt}. Avoid: {req.negative_prompt.strip()}"
    size = req.model_size if req.model_size in MODEL_IDS else DEFAULT_MODEL
    try:
        engine = get_engine(size)
        wav_bytes, duration = engine.generate(
            prompt=prompt,
            duration_seconds=req.duration_seconds,
            seed=req.seed,
        )
    except Exception as exc:
        logger.exception("generate_layer failed")
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
        "seed": req.seed,
        "model": engine.model_id,
        "duration_seconds": duration,
        "prompt": prompt,
        "bpm": req.bpm,
    }

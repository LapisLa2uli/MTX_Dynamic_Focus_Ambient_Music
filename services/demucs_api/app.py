"""FastAPI sidecar for self-hosted Demucs stem separation (localhost only)."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from separate import DEFAULT_MODEL, STEM_NAMES, SUPPORTED_MODELS, get_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demucs_api")

app = FastAPI(title="Adaptive Soundscape Demucs API", version="0.1.0")

ENV_MODEL = os.environ.get("DEMUCS_MODEL", DEFAULT_MODEL)


class SeparateRequest(BaseModel):
    audio_base64: str
    filename: str = "mix.wav"
    model: str = Field(default=DEFAULT_MODEL)


@app.on_event("startup")
def _startup() -> None:
    try:
        get_engine(ENV_MODEL if ENV_MODEL in SUPPORTED_MODELS else DEFAULT_MODEL)
    except Exception:
        logger.exception("Failed to preload Demucs; /health will report unloaded")


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        model = ENV_MODEL if ENV_MODEL in SUPPORTED_MODELS else DEFAULT_MODEL
        engine = get_engine(model)
        return {
            "ok": True,
            "loaded": engine.loaded,
            "stub": engine.stub_mode,
            "device": engine.device,
            "model": engine.model,
            "models": list(SUPPORTED_MODELS),
            "stems": list(STEM_NAMES),
        }
    except Exception as exc:
        return {"ok": False, "loaded": False, "error": str(exc)}


@app.post("/v1/separate")
def separate(req: SeparateRequest) -> dict[str, Any]:
    model = req.model if req.model in SUPPORTED_MODELS else DEFAULT_MODEL
    try:
        audio_bytes = base64.b64decode(req.audio_base64)
    except Exception as exc:
        return {"ok": False, "error": f"invalid audio_base64: {exc}"}
    if not audio_bytes:
        return {"ok": False, "error": "empty audio_base64"}
    try:
        engine = get_engine(model)
        stems, duration = engine.separate(audio_bytes, filename=req.filename or "mix.wav")
    except Exception as exc:
        logger.exception("separate failed")
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "stems": {
            name: base64.b64encode(stems[name]).decode("ascii") for name in STEM_NAMES
        },
        "model": engine.model,
        "duration_seconds": duration,
    }

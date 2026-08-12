"""HTTP client for the self-hosted MusicGen FastAPI sidecar."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GenerateLayerResponse:
    wav_bytes: bytes
    seed: int
    model: str
    duration_seconds: float
    prompt: str


class MusicGenClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:7862",
        timeout_seconds: float = 180.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def health(self) -> dict:
        return self._request_json("GET", "/health")

    def generate_layer(
        self,
        *,
        prompt: str,
        negative_prompt: str = "",
        duration_seconds: float = 27.428,
        bpm: float = 70.0,
        seed: int = 0,
        model_size: str = "small",
    ) -> GenerateLayerResponse:
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration_seconds": duration_seconds,
            "bpm": bpm,
            "seed": seed,
            "model_size": model_size,
        }
        data = self._request_json("POST", "/v1/generate_layer", body=payload)
        audio_b64 = data.get("audio_base64")
        if not audio_b64:
            raise RuntimeError("MusicGen API returned no audio_base64")
        import base64

        wav_bytes = base64.b64decode(audio_b64)
        return GenerateLayerResponse(
            wav_bytes=wav_bytes,
            seed=int(data.get("seed", seed)),
            model=str(data.get("model", model_size)),
            duration_seconds=float(data.get("duration_seconds", duration_seconds)),
            prompt=str(data.get("prompt", prompt)),
        )

    def _request_json(
        self, method: str, path: str, body: dict | None = None
    ) -> dict:
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except TimeoutError as exc:
            raise RuntimeError(
                f"MusicGen timed out after {self.timeout_seconds:.0f}s at {url}. "
                "A full ~27s layer often needs 2–8 minutes on GPU. "
                "Check nvidia-smi for musicgen python, and "
                "services/musicgen_api/_sidecar_7862.log. "
                "If torch is CPU-only (often shadowed from %APPDATA%\\Python), "
                "restart the API with PYTHONNOUSERSITE=1."
            ) from exc
        except urllib.error.URLError as exc:
            reason = str(getattr(exc, "reason", exc))
            if "timed out" in reason.lower() or "timeout" in reason.lower():
                raise RuntimeError(
                    f"MusicGen timed out after {self.timeout_seconds:.0f}s at {url}. "
                    "A full ~27s layer often needs 2–8 minutes on GPU. "
                    "Check nvidia-smi for musicgen python, and "
                    "services/musicgen_api/_sidecar_7862.log. "
                    "If torch is CPU-only (often shadowed from %APPDATA%\\Python), "
                    "restart the API with PYTHONNOUSERSITE=1."
                ) from exc
            raise RuntimeError(
                f"MusicGen API unreachable at {url} ({reason}). "
                "The app should auto-start services/musicgen_api; "
                "or run services/musicgen_api/run.ps1 manually."
            ) from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from MusicGen API: {raw[:200]}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("MusicGen API response was not an object")
        if parsed.get("ok") is False:
            raise RuntimeError(parsed.get("error") or "MusicGen API error")
        return parsed


def write_generation_meta(path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

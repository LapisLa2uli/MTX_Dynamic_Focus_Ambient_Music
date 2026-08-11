"""HTTP client for the self-hosted Demucs FastAPI sidecar."""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

STEM_NAMES = ("drums", "bass", "other", "vocals")


@dataclass
class SeparateResponse:
    stems: dict[str, bytes]
    model: str
    duration_seconds: float


class DemucsClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:7863",
        timeout_seconds: float = 600.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def health(self) -> dict:
        return self._request_json("GET", "/health")

    def separate(
        self,
        audio_bytes: bytes,
        *,
        filename: str = "mix.wav",
        model: str = "htdemucs",
    ) -> SeparateResponse:
        payload = {
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "filename": filename,
            "model": model,
        }
        data = self._request_json("POST", "/v1/separate", body=payload)
        raw_stems = data.get("stems") or {}
        if not isinstance(raw_stems, dict):
            raise RuntimeError("Demucs API returned invalid stems object")
        stems: dict[str, bytes] = {}
        for name in STEM_NAMES:
            b64 = raw_stems.get(name)
            if not b64:
                raise RuntimeError(f"Demucs API missing stem '{name}'")
            stems[name] = base64.b64decode(b64)
        return SeparateResponse(
            stems=stems,
            model=str(data.get("model", model)),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
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
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Demucs API unreachable at {url}. "
                "Start services/demucs_api (run.ps1) first."
            ) from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from Demucs API: {raw[:200]}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("Demucs API response was not an object")
        if parsed.get("ok") is False:
            raise RuntimeError(parsed.get("error") or "Demucs API error")
        return parsed

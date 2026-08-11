"""MusicGenClient against a fake HTTP server; WAV validation."""

from __future__ import annotations

import base64
import io
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import numpy as np
import pytest

from adaptive_soundscape.audio.generate_layers import (
    LayerValidationError,
    validate_wav_bytes,
)
from adaptive_soundscape.audio.musicgen_client import MusicGenClient


def _sine_wav_bytes(seconds: float = 1.0, rate: int = 32000) -> bytes:
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    samples = (0.2 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        return

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            body = json.dumps({"ok": True, "loaded": True, "stub": True}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):  # noqa: N802
        if self.path != "/v1/generate_layer":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        req = json.loads(raw.decode("utf-8"))
        wav = _sine_wav_bytes(float(req.get("duration_seconds", 1.0)))
        body = json.dumps(
            {
                "ok": True,
                "audio_base64": base64.b64encode(wav).decode("ascii"),
                "seed": int(req.get("seed", 0)),
                "model": "stub",
                "duration_seconds": float(req.get("duration_seconds", 1.0)),
                "prompt": req.get("prompt", ""),
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def musicgen_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()


def test_client_health_and_generate(musicgen_server: str):
    client = MusicGenClient(musicgen_server, timeout_seconds=5)
    health = client.health()
    assert health["ok"] is True
    result = client.generate_layer(
        prompt="test",
        duration_seconds=1.0,
        bpm=70,
        seed=3,
    )
    assert result.wav_bytes[:4] == b"RIFF"
    assert result.seed == 3


def test_validate_rejects_wrong_duration():
    wav = _sine_wav_bytes(1.0)
    with pytest.raises(LayerValidationError):
        validate_wav_bytes(wav, expected_seconds=10.0, tolerance=0.02)


def test_validate_accepts_close_duration():
    wav = _sine_wav_bytes(1.0)
    duration, peak = validate_wav_bytes(wav, expected_seconds=1.0, tolerance=0.05)
    assert abs(duration - 1.0) < 0.05
    assert peak > 0

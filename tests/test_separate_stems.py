"""DemucsClient + stem mapping / stub detection / install orchestration."""

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

from adaptive_soundscape.audio.album import add_track
from adaptive_soundscape.audio.demucs_client import DemucsClient
from adaptive_soundscape.audio.layer_mix import BASE_LAYER_IDS
from adaptive_soundscape.audio.music_manifest import (
    MusicIntensity,
    load_manifest,
    migrate_songs_to_layered_stubs,
)
from adaptive_soundscape.audio.separate_stems import (
    SEPARATION_META_NAME,
    _highpass_wav,
    _wav_rms,
    file_sha256,
    map_stems_to_layers,
    needs_separation,
    separate_and_install_stems,
)


def _sine_wav_bytes(
    seconds: float = 1.0,
    rate: int = 44100,
    freq: float = 220.0,
    amp: float = 0.2,
) -> bytes:
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    samples = (amp * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def _silent_wav_bytes(seconds: float = 1.0, rate: int = 44100) -> bytes:
    n = int(rate * seconds)
    samples = np.zeros(n, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


class _DemucsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        return

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            body = json.dumps(
                {"ok": True, "loaded": True, "stub": True, "model": "htdemucs"}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):  # noqa: N802
        if self.path != "/v1/separate":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        stems = {
            "drums": _sine_wav_bytes(seconds=1.0, freq=80.0, amp=0.15),
            "bass": _sine_wav_bytes(seconds=1.0, freq=110.0, amp=0.18),
            "other": _sine_wav_bytes(seconds=1.0, freq=440.0, amp=0.22),
            "vocals": _silent_wav_bytes(),
        }
        body = json.dumps(
            {
                "ok": True,
                "stems": {
                    k: base64.b64encode(v).decode("ascii") for k, v in stems.items()
                },
                "model": "htdemucs",
                "duration_seconds": 1.0,
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def demucs_server():
    server = HTTPServer(("127.0.0.1", 0), _DemucsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()


def test_demucs_client_separate(demucs_server: str):
    client = DemucsClient(demucs_server, timeout_seconds=10.0)
    health = client.health()
    assert health["ok"] is True
    result = client.separate(_sine_wav_bytes(), filename="mix.wav")
    assert set(result.stems) == {"drums", "bass", "other", "vocals"}
    assert result.model == "htdemucs"
    assert all(len(v) > 44 for v in result.stems.values())


def test_map_stems_instrumental_puts_other_in_melody():
    stems = {
        "drums": _sine_wav_bytes(freq=80.0),
        "bass": _sine_wav_bytes(freq=110.0),
        # Broadband-ish lead via mid + low content: mix two tones into other.
        "other": _sine_wav_bytes(freq=880.0, amp=0.22),
        "vocals": _silent_wav_bytes(),
    }
    # Blend a low chord body into other.
    import numpy as np
    import io
    import wave

    def _mix(a: bytes, b: bytes) -> bytes:
        def dec(w):
            with wave.open(io.BytesIO(w), "rb") as wf:
                return np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(
                    np.float32
                )
        x = dec(a) + dec(b)
        peak = np.max(np.abs(x)) or 1.0
        x = (x * (30000.0 / peak)).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(x.tobytes())
        return buf.getvalue()

    stems["other"] = _mix(
        _sine_wav_bytes(freq=880.0, amp=0.22),
        _sine_wav_bytes(freq=110.0, amp=0.18),
    )
    layers, mapping = map_stems_to_layers(stems)
    assert set(layers) == set(BASE_LAYER_IDS)
    assert layers["rhythm"] == stems["drums"]
    assert layers["pad"] == stems["bass"]
    assert layers["melody_a"] != stems["other"]
    assert layers["harmony"] != stems["other"]
    assert "highpass" in mapping["melody_a"]
    assert "lowpass" in mapping["harmony"]
    from adaptive_soundscape.audio.separate_stems import _band_rms

    # Lead midrange stays in melody; warm body stays in harmony.
    assert _band_rms(layers["melody_a"], 350.0, 2500.0) > _band_rms(
        layers["harmony"], 350.0, 2500.0
    )
    assert _band_rms(layers["harmony"], 40.0, 280.0) > _band_rms(
        layers["melody_a"], 40.0, 280.0
    )


def test_map_stems_quiet_vocal_bleed_treated_as_instrumental():
    # Bleed above absolute silence floor but still << other energy.
    bleed = _sine_wav_bytes(freq=330.0, amp=0.01)
    other = _sine_wav_bytes(freq=220.0, amp=0.25)
    stems = {
        "drums": _sine_wav_bytes(freq=80.0),
        "bass": _sine_wav_bytes(freq=110.0),
        "other": other,
        "vocals": bleed,
    }
    assert _wav_rms(bleed) > 1e-3
    layers, mapping = map_stems_to_layers(stems)
    assert layers["melody_a"] != other
    assert "highpass" in mapping["melody_a"]


def test_map_stems_keeps_vocals_when_audible():
    vocals = _sine_wav_bytes(freq=330.0, amp=0.2)
    other = _sine_wav_bytes(freq=220.0, amp=0.15)
    stems = {
        "drums": _sine_wav_bytes(freq=80.0),
        "bass": _sine_wav_bytes(freq=110.0),
        "other": other,
        "vocals": vocals,
    }
    layers, mapping = map_stems_to_layers(stems)
    assert layers["melody_a"] == vocals
    assert layers["harmony"] == other
    assert mapping["melody_a"] == "vocals"


def test_repair_melody_harmony_layers(tmp_path: Path):
    from adaptive_soundscape.audio.separate_stems import (
        _band_rms,
        repair_melody_harmony_layers,
    )

    song = tmp_path / "programming" / "programming_01"
    (song / "melody_a").mkdir(parents=True)
    (song / "harmony").mkdir(parents=True)
    # Mis-mapped: quiet bleed in melody_a, full other (lead+body) in harmony.
    (song / "melody_a" / "melody_a_01.wav").write_bytes(
        _sine_wav_bytes(freq=400.0, amp=0.01)
    )
    other = _sine_wav_bytes(freq=880.0, amp=0.25)
    (song / "harmony" / "harmony_01.wav").write_bytes(other)
    (song / "manifest.json").write_text(
        json.dumps(
            {
                "songId": "programming_01",
                "playbackMode": "layered",
                "layers": {
                    "melody_a": {"src": "melody_a/melody_a_01.wav", "role": "base"},
                    "harmony": {"src": "harmony/harmony_01.wav", "role": "base"},
                },
                "tracks": {},
            }
        ),
        encoding="utf-8",
    )

    written = repair_melody_harmony_layers(song)
    assert len(written) == 2
    mel = (song / "melody_a" / "melody_a_01.wav").read_bytes()
    har = (song / "harmony" / "harmony_01.wav").read_bytes()
    assert mel != other
    assert _band_rms(mel, 350.0, 2500.0) > _band_rms(har, 350.0, 2500.0)
    # Second call should no-op once split is clean.
    assert repair_melody_harmony_layers(song) == []


def test_needs_separation_stubs_and_meta(tmp_path: Path):
    src = tmp_path / "seed.wav"
    src.write_bytes(_sine_wav_bytes())
    dest = add_track(tmp_path, "programming", src, intensity=MusicIntensity.FOCUS)
    song = dest.parent.parent
    migrate_songs_to_layered_stubs(tmp_path)
    assert needs_separation(song) is True

    # Distinct custom stems without meta → do not overwrite
    for layer_id in BASE_LAYER_IDS:
        path = song / layer_id / f"{layer_id}_01.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Different content per layer
        path.write_bytes(_sine_wav_bytes(freq=100.0 + hash(layer_id) % 200))
    assert needs_separation(song) is False

    # Meta present → skip even if force=False
    (song / SEPARATION_META_NAME).write_text("{}", encoding="utf-8")
    assert needs_separation(song) is False
    assert needs_separation(song, force=True) is True


def test_separate_and_install_overwrites_stubs(tmp_path: Path, demucs_server: str):
    src = tmp_path / "seed.wav"
    src.write_bytes(_sine_wav_bytes())
    dest = add_track(tmp_path, "programming", src, intensity=MusicIntensity.FOCUS)
    song = dest.parent.parent
    migrate_songs_to_layered_stubs(tmp_path)
    seed_hash = file_sha256(dest)
    for layer_id in BASE_LAYER_IDS:
        layer_path = song / layer_id / f"{layer_id}_01.wav"
        # stubs may be .wav copies
        candidates = list((song / layer_id).glob(f"{layer_id}_*"))
        assert candidates
        assert file_sha256(candidates[0]) == seed_hash

    client = DemucsClient(demucs_server, timeout_seconds=10.0)
    written = separate_and_install_stems(song, client=client, model="htdemucs")
    assert len(written) == 4
    manifest = load_manifest(song)
    assert manifest is not None
    assert manifest.playback_mode == "layered"
    for layer_id in BASE_LAYER_IDS:
        path = manifest.resolve_layer_path(song, layer_id)
        assert path is not None
        assert path.suffix.lower() == ".wav"
        assert file_sha256(path) != seed_hash
    assert (song / SEPARATION_META_NAME).is_file()
    # Second call skips
    assert separate_and_install_stems(song, client=client) == []


def test_highpass_preserves_wav_header():
    src = _sine_wav_bytes(freq=440.0)
    out = _highpass_wav(src, cutoff_hz=300.0)
    assert out[:4] == b"RIFF"
    assert _wav_rms(out) > 0

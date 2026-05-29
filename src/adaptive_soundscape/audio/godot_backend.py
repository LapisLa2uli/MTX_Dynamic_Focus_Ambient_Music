"""Godot Engine sidecar audio backend (TCP JSON API)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from adaptive_soundscape.audio.parameters import AudioParameters

logger = logging.getLogger(__name__)


class GodotAudioBackend:
    """Launch Godot headless and control layered audio via JSON lines over TCP."""

    def __init__(
        self,
        project_path: Path,
        assets_dir: Path,
        godot_executable: str | None = None,
        host: str = "127.0.0.1",
        port: int = 8765,
        master_volume: float = 0.35,
        startup_timeout: float = 8.0,
    ) -> None:
        self.project_path = project_path
        self.assets_dir = assets_dir
        self.host = host
        self.port = port
        self.master_volume = master_volume
        self.startup_timeout = startup_timeout
        self._exe = godot_executable or _find_godot_executable()
        self._process: subprocess.Popen[str] | None = None
        self._socket: socket.socket | None = None
        self._recv_buffer = b""
        self._profile_id = "unknown"
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return self._playing

    def start(self, profile_id: str | None = None) -> None:
        if self._playing:
            return
        if not self._exe:
            raise RuntimeError(
                "Godot executable not found. Set audio.godot_executable in config "
                "or install Godot 4 and add it to PATH."
            )
        if profile_id:
            self._profile_id = profile_id
        self._stop_owned_process()
        self._shutdown_sidecar_on_port()
        self._launch_process()
        self._connect()
        self._send(
            {
                "op": "configure",
                "assets_path": str(self.assets_dir.resolve()).replace("\\", "/"),
                "master_volume": self.master_volume,
            }
        )
        profile_resp = self._send({"op": "set_profile", "profile_id": self._profile_id})
        self._ensure_layers_loaded(profile_resp, "set_profile")
        start_resp = self._send({"op": "start"})
        self._ensure_layers_loaded(start_resp, "start")
        if not start_resp.get("playing", False):
            raise RuntimeError(
                f"Godot sidecar failed to start playback for profile '{self._profile_id}'"
            )
        self._playing = True

    def stop(self) -> None:
        if self._socket is not None:
            try:
                self._send({"op": "stop"})
                self._send({"op": "quit"})
            except OSError:
                pass
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        if self._process is not None:
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._playing = False

    def set_profile(self, profile_id: str) -> None:
        self._profile_id = profile_id
        if self._socket is not None:
            self._send({"op": "set_profile", "profile_id": profile_id})

    def set_parameters(self, params: AudioParameters) -> None:
        if self._socket is not None:
            self._send(_params_payload("set_parameters", params))

    def crossfade_to(
        self,
        profile_id: str,
        duration_seconds: float,
        params: AudioParameters | None = None,
    ) -> None:
        self._profile_id = profile_id
        if self._socket is not None:
            payload = {
                "op": "crossfade",
                "profile_id": profile_id,
                "duration": duration_seconds,
            }
            if params is not None:
                payload.update(
                    {
                        "brightness": params.brightness,
                        "energy": params.energy,
                        "warmth": params.warmth,
                    }
                )
            self._send(payload)

    def crossfade_to_with_params(
        self, profile_id: str, duration_seconds: float, params: AudioParameters
    ) -> None:
        self.crossfade_to(profile_id, duration_seconds, params)

    def _launch_process(self) -> None:
        project_file = self.project_path / "project.godot"
        if not project_file.exists():
            raise FileNotFoundError(f"Godot project not found: {project_file}")
        assets = str(self.assets_dir.resolve()).replace("\\", "/")
        cmd = [
            self._exe,
            "--audio-driver",
            _audio_driver(),
            "--path",
            str(self.project_path),
            "--",
            "--port",
            str(self.port),
            "--assets",
            assets,
        ]
        logger.info("Launching Godot sidecar: %s", " ".join(cmd))
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(self.project_path),
        )
        time.sleep(1.5)

    def _stop_owned_process(self) -> None:
        if self._socket is not None:
            try:
                self._send({"op": "quit"})
            except OSError:
                pass
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
            self._recv_buffer = b""
        if self._process is None:
            return
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.kill()
        self._process = None

    def _shutdown_sidecar_on_port(self) -> None:
        """Stop a stale Godot sidecar so we can bind the configured port."""
        sock: socket.socket | None = None
        try:
            sock = socket.create_connection((self.host, self.port), timeout=0.35)
            sock.settimeout(1.0)
            self._socket = sock
            self._recv_buffer = b""
            self._read_line()  # connected event
            self._send({"op": "quit"})
        except OSError:
            pass
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            self._socket = None
            self._recv_buffer = b""
        self._wait_for_port_free()

    def _wait_for_port_free(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                sock = socket.create_connection((self.host, self.port), timeout=0.25)
                sock.close()
                time.sleep(0.2)
            except OSError:
                return
        raise RuntimeError(
            f"Port {self.port} is still in use. Close other Godot sidecars and try again."
        )

    def _ensure_layers_loaded(self, response: dict, stage: str) -> None:
        layer_count = int(response.get("layer_count", 0) or 0)
        if layer_count > 0:
            return
        assets_path = response.get("assets_path", str(self.assets_dir))
        profile_id = response.get("profile_id", self._profile_id)
        raise RuntimeError(
            f"No audio layers loaded during {stage} for profile '{profile_id}' "
            f"(assets={assets_path}). Check that audio files exist in the assets folder."
        )

    def _drain_process_stderr(self) -> str:
        return ""

    def _connect(self) -> None:
        deadline = time.monotonic() + self.startup_timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self._process and self._process.poll() is not None:
                code = self._process.returncode
                raise RuntimeError(f"Godot process exited early with code {code}")
            try:
                sock = socket.create_connection((self.host, self.port), timeout=0.5)
                sock.settimeout(2.0)
                self._socket = sock
                self._read_line()  # connected event
                return
            except OSError as exc:
                last_error = exc
                time.sleep(0.15)
        raise TimeoutError(f"Could not connect to Godot on {self.host}:{self.port}") from last_error

    def _send(self, payload: dict) -> dict:
        if self._socket is None:
            return {}
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        self._socket.sendall(line.encode("utf-8"))
        return self._read_line()

    def _read_line(self) -> dict:
        if self._socket is None:
            return {}
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if b"\n" in self._recv_buffer:
                line, sep, remainder = self._recv_buffer.partition(b"\n")
                self._recv_buffer = remainder
                if not line.strip():
                    continue
                data = json.loads(line.decode("utf-8"))
                if not data.get("ok", False) and data.get("error"):
                    raise RuntimeError(f"Godot audio error: {data['error']}")
                return data
            try:
                chunk = self._socket.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                break
            self._recv_buffer += chunk
        raise RuntimeError("No response from Godot audio sidecar")


def _find_godot_executable() -> str | None:
    env = os.environ.get("GODOT4") or os.environ.get("GODOT_EXECUTABLE")
    if env and Path(env).exists():
        return env
    for name in ("godot4", "godot", "Godot_v4.3-stable_win64.exe", "Godot.exe"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in (
        Path("C:/Program Files/Godot/Godot_v4.3-stable_win64.exe"),
        Path.home() / "scoop/apps/godot/current/godot.exe",
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _audio_driver() -> str:
    """Godot --headless uses Dummy audio (silent); always pick a real driver."""
    if os.name == "nt":
        return "WASAPI"
    if sys.platform == "darwin":
        return "CoreAudio"
    return "PulseAudio"


def _params_payload(op: str, params: AudioParameters) -> dict:
    return {
        "op": op,
        "brightness": params.brightness,
        "energy": params.energy,
        "warmth": params.warmth,
    }

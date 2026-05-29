"""Quick audio diagnostics."""
import json
import socket
import time
from pathlib import Path

from adaptive_soundscape.core.config import load_settings, resolve_assets_dir, _project_root
from adaptive_soundscape.core.events import FocusState, WorkContext
from adaptive_soundscape.audio.factory import create_audio_backend
from adaptive_soundscape.audio.godot_backend import GodotAudioBackend
from adaptive_soundscape.audio.placeholder_mixer import PlaceholderMixer
from adaptive_soundscape.transition.controller import TransitionController


def query_godot(port: int) -> None:
    try:
        sock = socket.create_connection(("127.0.0.1", port), timeout=1)
        sock.settimeout(2)
        buf = b""
        while b"\n" not in buf:
            buf += sock.recv(4096)
        print("existing godot:", buf.decode().strip())
        sock.sendall(b'{"op":"status"}\n')
        buf = b""
        t0 = time.time()
        while time.time() - t0 < 2:
            chunk = sock.recv(4096)
            if chunk:
                buf += chunk
                if b"\n" in buf:
                    print("status:", json.loads(buf.split(b"\n")[0]))
                    break
        sock.close()
    except OSError as exc:
        print("no running godot:", exc)


def main() -> None:
    s = load_settings()
    assets = resolve_assets_dir(s)
    print("backend:", s.audio.backend)
    print("assets:", assets)
    print("files:", sorted(p.name for p in assets.glob("*.wav"))[:5], "...")

    query_godot(s.audio.godot_port)

    tc = TransitionController()
    decision = tc.decide(WorkContext.UNKNOWN, FocusState.CALM_PRODUCTIVITY, 0.5)
    print("decision profile:", decision.profile_id)

    try:
        g = GodotAudioBackend(
            project_path=_project_root() / s.audio.godot_project,
            assets_dir=assets,
            godot_executable=s.audio.godot_executable,
            port=s.audio.godot_port,
            master_volume=0.8,
        )
        g.start(profile_id=decision.profile_id)
        status = g._send({"op": "status"})
        print("godot start:", status)
        g.crossfade_to(decision.profile_id, decision.crossfade_seconds, decision.parameters)
        time.sleep(0.5)
        status2 = g._send({"op": "status"})
        print("after crossfade:", status2)
        g.stop()
    except Exception as exc:
        print("godot FAILED:", type(exc).__name__, exc)

    try:
        import sounddevice as sd

        print("sounddevice output:", sd.query_devices(kind="output"))
    except Exception as exc:
        print("sounddevice FAILED:", exc)

    pm = PlaceholderMixer(assets_dir=assets, master_volume=0.8)
    pm.start(profile_id="programming")
    print("placeholder playing:", pm.is_playing)
    time.sleep(1)
    pm.stop()


if __name__ == "__main__":
    main()

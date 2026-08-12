"""Start/stop Demucs and MusicGen uvicorn sidecars for layer processing."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

ProgressFn = Callable[[int, str], None]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _conda_env_python(env_name: str) -> Path | None:
    """Resolve ``python`` inside a named conda env (Windows + Unix)."""
    name = (env_name or "").strip()
    if not name:
        return None
    roots: list[Path] = []
    home = Path.home()
    roots.append(home / ".conda" / "envs")
    roots.append(home / "miniconda3" / "envs")
    roots.append(home / "anaconda3" / "envs")
    for key in ("CONDA_PREFIX", "CONDA_ROOT", "_CONDA_ROOT"):
        raw = os.environ.get(key)
        if not raw:
            continue
        base = Path(raw)
        roots.append(base.parent / "envs" if base.name != "envs" else base)
        if base.name == "envs":
            roots.append(base)
        else:
            roots.append(base / "envs")
    roots.extend(
        [
            Path(r"D:\anaconda3\envs"),
            Path(r"C:\anaconda3\envs"),
            Path(r"C:\ProgramData\miniconda3\envs"),
            Path(r"C:\ProgramData\anaconda3\envs"),
        ]
    )
    seen: set[Path] = set()
    for root in roots:
        try:
            root = root.resolve()
        except OSError:
            continue
        if root in seen:
            continue
        seen.add(root)
        for exe in ("python.exe", "python"):
            candidate = root / name / exe
            if candidate.is_file():
                return candidate
    return None


def resolve_conda_python(*env_names: str) -> tuple[str, Path]:
    """Return ``(env_name, python_path)`` for the first existing conda env."""
    tried: list[str] = []
    for name in env_names:
        cleaned = (name or "").strip()
        if not cleaned or cleaned in tried:
            continue
        tried.append(cleaned)
        found = _conda_env_python(cleaned)
        if found is not None:
            return cleaned, found
    raise RuntimeError(
        "Could not find conda env "
        + (" / ".join(f"“{n}”" for n in tried) or "(none)")
        + ". Create one and install service requirements "
        "(see services/*/README.md). "
        "If imports pick up a CPU torch from %APPDATA%\\Python, set "
        "PYTHONNOUSERSITE=1 when starting the sidecar."
    )


def probe_http_json(url: str, *, timeout: float = 3.0) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _musicgen_extra_env(service_dir: Path) -> dict[str, str]:
    """Match services/musicgen_api/run.ps1 so CUDA + local weights are used."""
    env: dict[str, str] = {
        "PYTHONNOUSERSITE": "1",
        "MUSICGEN_DEVICE": os.environ.get("MUSICGEN_DEVICE", "cuda"),
        "MUSICGEN_MODEL_SIZE": os.environ.get("MUSICGEN_MODEL_SIZE", "small"),
    }
    if os.environ.get("MUSICGEN_MODEL_PATH"):
        env["MUSICGEN_MODEL_PATH"] = os.environ["MUSICGEN_MODEL_PATH"]
    else:
        local = service_dir / "model_cache" / "local_musicgen_small"
        if local.is_dir():
            env["MUSICGEN_MODEL_PATH"] = str(local)
            env["HF_HUB_OFFLINE"] = "1"
            env["TRANSFORMERS_OFFLINE"] = "1"
    return env


def _demucs_extra_env() -> dict[str, str]:
    return {
        "PYTHONNOUSERSITE": "1",
        "DEMUCS_DEVICE": os.environ.get("DEMUCS_DEVICE", "cuda"),
        "DEMUCS_MODEL": os.environ.get("DEMUCS_MODEL", "htdemucs"),
    }


def _preflight_cuda(python: Path, *, label: str) -> None:
    """Fail fast if this interpreter cannot see a CUDA torch build."""
    script = (
        "import os, torch\n"
        "print(torch.__version__)\n"
        "print(torch.__file__)\n"
        "print('1' if torch.cuda.is_available() else '0')\n"
    )
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    try:
        proc = subprocess.run(
            [str(python), "-c", script],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"{label}: could not probe torch/CUDA ({exc})") from exc
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if proc.returncode != 0 or len(lines) < 3:
        err = (proc.stderr or proc.stdout or "").strip()[:400]
        raise RuntimeError(
            f"{label}: torch probe failed (exit {proc.returncode}). {err}"
        )
    version, torch_file, cuda_flag = lines[0], lines[1], lines[2]
    if cuda_flag != "1":
        raise RuntimeError(
            f"{label}: CUDA is unavailable in {python} "
            f"(torch={version} at {torch_file}). "
            "A CPU torch from %APPDATA%\\Python often shadows the conda CUDA build — "
            "sidecars set PYTHONNOUSERSITE=1. Install a CUDA wheel into the musicgen "
            "env, e.g. pip install torch --index-url "
            "https://download.pytorch.org/whl/cu124"
        )
    logger.info("%s CUDA ok (torch=%s)", label, version)


@dataclass
class SidecarSpec:
    name: str
    port: int
    service_dir: Path
    conda_env: str
    fallback_envs: tuple[str, ...] = ()
    health_path: str = "/health"
    extra_env: dict[str, str] = field(default_factory=dict)
    require_cuda: bool = True

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def health_url(self) -> str:
        return f"{self.base_url}{self.health_path}"


@dataclass
class OwnedProcess:
    spec: SidecarSpec
    process: subprocess.Popen | None
    already_running: bool = False


class SidecarLifecycle:
    """Ensure Demucs/MusicGen APIs are up for a job, then stop ones we started."""

    def __init__(
        self,
        *,
        demucs_env: str = "demucs",
        musicgen_env: str = "musicgen",
        startup_timeout_seconds: float = 300.0,
        stop_when_done: bool = True,
    ) -> None:
        root = _project_root()
        self.startup_timeout_seconds = float(startup_timeout_seconds)
        self.stop_when_done = bool(stop_when_done)
        self._owned: list[OwnedProcess] = []
        demucs_dir = root / "services" / "demucs_api"
        musicgen_dir = root / "services" / "musicgen_api"
        # Prefer dedicated demucs env; fall back to musicgen (common local setup).
        demucs_fallbacks = tuple(
            n for n in (demucs_env, "demucs", "musicgen") if n and n != demucs_env
        )
        # Dedupe while preserving order with primary first via resolve_conda_python.
        self.demucs = SidecarSpec(
            name="Demucs",
            port=7863,
            service_dir=demucs_dir,
            conda_env=demucs_env,
            fallback_envs=demucs_fallbacks,
            extra_env=_demucs_extra_env(),
            require_cuda=True,
        )
        self.musicgen = SidecarSpec(
            name="MusicGen",
            port=7862,
            service_dir=musicgen_dir,
            conda_env=musicgen_env,
            fallback_envs=tuple(
                n for n in ("musicgen",) if n and n != musicgen_env
            ),
            extra_env=_musicgen_extra_env(musicgen_dir),
            require_cuda=True,
        )

    def is_healthy(self, spec: SidecarSpec, *, require_loaded: bool = True) -> bool:
        data = probe_http_json(spec.health_url, timeout=2.5)
        if not data or data.get("ok") is False:
            return False
        if require_loaded and not data.get("stub") and not data.get("loaded", False):
            return False
        if (
            require_loaded
            and spec.require_cuda
            and not data.get("stub")
            and str(data.get("device", "")).lower() == "cpu"
        ):
            # Treat CPU-loaded models as not ready when we expect GPU inference.
            return False
        return True

    def ensure(
        self,
        spec: SidecarSpec,
        *,
        on_progress: ProgressFn | None = None,
        progress_base: int = 0,
    ) -> None:
        """Start the sidecar if needed and wait until healthy/loaded."""
        if self.is_healthy(spec, require_loaded=True):
            if on_progress:
                on_progress(progress_base, f"{spec.name} already running (GPU)")
            self._owned.append(
                OwnedProcess(spec=spec, process=None, already_running=True)
            )
            return

        # Up but still loading, or loaded on CPU while we require CUDA.
        data = probe_http_json(spec.health_url, timeout=2.0)
        if data and data.get("ok") is not False:
            device = str(data.get("device", "")).lower()
            if (
                spec.require_cuda
                and device == "cpu"
                and data.get("loaded")
                and not data.get("stub")
            ):
                raise RuntimeError(
                    f"{spec.name} is running on CPU at {spec.health_url}. "
                    "Stop that process and let the app restart it with "
                    "PYTHONNOUSERSITE=1 / CUDA torch, or set "
                    f"MUSICGEN_DEVICE/DEMUCS_DEVICE appropriately. "
                    f"health={data}"
                )
            self._owned.append(
                OwnedProcess(spec=spec, process=None, already_running=True)
            )
            self._wait_until_ready(
                spec, on_progress=on_progress, progress_base=progress_base
            )
            return

        if on_progress:
            on_progress(progress_base, f"Starting {spec.name} API…")
        proc = self._spawn(spec)
        self._owned.append(
            OwnedProcess(spec=spec, process=proc, already_running=False)
        )
        self._wait_until_ready(
            spec, on_progress=on_progress, progress_base=progress_base
        )

    def _spawn(self, spec: SidecarSpec) -> subprocess.Popen:
        env_name, python = resolve_conda_python(spec.conda_env, *spec.fallback_envs)
        if env_name != spec.conda_env:
            logger.warning(
                "%s: conda env “%s” missing; using “%s”",
                spec.name,
                spec.conda_env,
                env_name,
            )
        if spec.require_cuda:
            _preflight_cuda(python, label=spec.name)
        if not spec.service_dir.is_dir():
            raise RuntimeError(f"Missing service directory: {spec.service_dir}")

        env = os.environ.copy()
        env.update(spec.extra_env)
        # Always prefer the env interpreter’s site-packages (never user CPU torch).
        env["PYTHONNOUSERSITE"] = "1"

        cmd = [
            str(python),
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(spec.port),
        ]
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

        log_path = spec.service_dir / f"_sidecar_{spec.port}.log"
        log_handle = log_path.open("w", encoding="utf-8")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(spec.service_dir),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        except Exception:
            log_handle.close()
            raise
        # Detach log handle ownership to the process lifetime.
        proc._acs_log_handle = log_handle  # type: ignore[attr-defined]
        logger.info(
            "Started %s sidecar pid=%s via %s env=%s (log=%s)",
            spec.name,
            proc.pid,
            python,
            env_name,
            log_path,
        )
        return proc

    def _wait_until_ready(
        self,
        spec: SidecarSpec,
        *,
        on_progress: ProgressFn | None,
        progress_base: int,
    ) -> None:
        deadline = time.monotonic() + self.startup_timeout_seconds
        last_msg = ""
        while time.monotonic() < deadline:
            # If we own a process that already exited, fail fast.
            for owned in self._owned:
                if (
                    owned.spec.name == spec.name
                    and owned.process is not None
                    and owned.process.poll() is not None
                ):
                    raise RuntimeError(
                        f"{spec.name} API exited early (code {owned.process.returncode}). "
                        f"Check services/{spec.service_dir.name}/_sidecar_{spec.port}.log"
                    )
            if self.is_healthy(spec, require_loaded=True):
                if on_progress:
                    on_progress(min(99, progress_base + 8), f"{spec.name} ready on GPU")
                return
            data = probe_http_json(spec.health_url, timeout=2.0)
            if data and on_progress:
                err = data.get("error")
                device = data.get("device")
                msg = f"Waiting for {spec.name} to load model…"
                if device:
                    msg = f"Waiting for {spec.name} (device={device})…"
                if err:
                    msg = f"Waiting for {spec.name}: {err}"
                if msg != last_msg:
                    on_progress(progress_base + 3, msg)
                    last_msg = msg
            elif on_progress and not last_msg:
                last_msg = f"Waiting for {spec.name} to accept connections…"
                on_progress(progress_base + 1, last_msg)
            time.sleep(1.5)
        raise RuntimeError(
            f"Timed out after {self.startup_timeout_seconds:.0f}s waiting for "
            f"{spec.name} at {spec.health_url}"
        )

    def stop_owned(self, *, on_progress: ProgressFn | None = None) -> None:
        if not self.stop_when_done:
            self._owned.clear()
            return
        for owned in reversed(self._owned):
            if owned.already_running or owned.process is None:
                continue
            if on_progress:
                on_progress(98, f"Stopping {owned.spec.name} API…")
            self._terminate(owned.process)
            handle = getattr(owned.process, "_acs_log_handle", None)
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass
        self._owned.clear()

    @staticmethod
    def _terminate(proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except OSError as exc:
            logger.warning("Failed to stop sidecar pid=%s: %s", proc.pid, exc)

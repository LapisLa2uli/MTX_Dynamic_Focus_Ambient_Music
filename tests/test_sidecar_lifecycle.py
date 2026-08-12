"""Tests for sidecar lifecycle helpers (no real uvicorn required)."""

from __future__ import annotations

from pathlib import Path

from adaptive_soundscape.audio.sidecar_lifecycle import (
    SidecarLifecycle,
    _conda_env_python,
    _musicgen_extra_env,
    probe_http_json,
)


def test_probe_http_json_unreachable():
    assert probe_http_json("http://127.0.0.1:1/health", timeout=0.2) is None


def test_conda_env_python_musicgen_if_present():
    found = _conda_env_python("musicgen")
    # Env may or may not exist on CI; just ensure no crash and Path|None.
    assert found is None or isinstance(found, Path)


def test_sidecar_lifecycle_specs():
    life = SidecarLifecycle()
    assert life.demucs.port == 7863
    assert life.musicgen.port == 7862
    assert life.demucs.service_dir.name == "demucs_api"
    assert life.musicgen.service_dir.name == "musicgen_api"
    assert life.musicgen.extra_env.get("PYTHONNOUSERSITE") == "1"
    assert life.demucs.extra_env.get("PYTHONNOUSERSITE") == "1"
    assert "musicgen" in (life.demucs.conda_env, *life.demucs.fallback_envs)


def test_musicgen_extra_env_sets_local_model_when_present(tmp_path: Path):
    local = tmp_path / "model_cache" / "local_musicgen_small"
    local.mkdir(parents=True)
    env = _musicgen_extra_env(tmp_path)
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["MUSICGEN_DEVICE"] == "cuda"
    assert env["MUSICGEN_MODEL_PATH"] == str(local)
    assert env.get("HF_HUB_OFFLINE") == "1"

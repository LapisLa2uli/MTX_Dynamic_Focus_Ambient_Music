"""Configuration loading via pydantic-settings and YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseModel):
    poll_interval_ms: int = 1000
    logging_enabled: bool = False


class PrivacyConfig(BaseModel):
    collect_window_titles: bool = True
    collect_process_names: bool = True
    log_activity: bool = False


class ContextConfig(BaseModel):
    dwell_seconds_min: int = 30
    dwell_seconds_max: int = 60
    default_dwell_seconds: int = 45


class TransitionConfig(BaseModel):
    deep_focus_crossfade_seconds: float = 12.0
    distraction_recovery_seconds: float = 4.5
    cooldown_seconds: float = 60.0
    hysteresis_threshold: float = 0.08


class CognitiveConfig(BaseModel):
    sensitivity: float = 1.0
    focus_smoothing: float = 0.85


class AudioConfig(BaseModel):
    backend: str = "placeholder"
    sample_rate: int = 44100
    block_size: int = 1024
    master_volume: float = 0.75
    prefer_mp3: bool = True
    assets_dir: str = "assets/audio"
    godot_project: str = "godot"
    godot_executable: str = ""
    godot_host: str = "127.0.0.1"
    godot_port: int = 8765
    godot_startup_timeout: float = 8.0
    fallback_to_placeholder: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACS_", extra="ignore")

    app: AppConfig = Field(default_factory=AppConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    transition: TransitionConfig = Field(default_factory=TransitionConfig)
    cognitive: CognitiveConfig = Field(default_factory=CognitiveConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from YAML, falling back to defaults."""
    path = config_path or _project_root() / "config" / "default.yaml"
    data: dict[str, Any] = {}
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
            if isinstance(raw, dict):
                data = raw
    return Settings(**data)


def resolve_assets_dir(settings: Settings) -> Path:
    root = _project_root()
    assets = Path(settings.audio.assets_dir)
    if assets.is_absolute():
        return assets
    return root / assets

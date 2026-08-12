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
    dwell_seconds_min: int = 3
    dwell_seconds_max: int = 8
    default_dwell_seconds: int = 5


class TransitionConfig(BaseModel):
    deep_focus_crossfade_seconds: float = 12.0
    distraction_recovery_seconds: float = 4.5
    cooldown_seconds: float = 60.0
    hysteresis_threshold: float = 0.08


class CognitiveConfig(BaseModel):
    sensitivity: float = 1.0
    focus_smoothing: float = 0.40
    uncalibrated_focus_smoothing: float = 0.18
    auto_distraction_enabled: bool = True
    auto_distraction_enter: float = 0.38
    auto_distraction_exit: float = 0.50
    auto_distraction_dwell_seconds: float = 4.0


class FocusIndexConfigModel(BaseModel):
    enabled: bool = True
    window_seconds: float = 180.0
    weight_alignment: float = 0.40
    weight_switch: float = 0.30
    weight_idle: float = 0.20
    weight_probe: float = 0.10
    probe_ttl_minutes: float = 45.0
    retention_days: int = 7
    aligned_switch_penalty: float = 0.2
    recency_tau_seconds: float = 45.0
    pattern_gate_low: float = 55.0
    pattern_assist_max: float = 8.0
    switch_rate_ref: float = 1.25
    short_burst_s: float = 45.0
    idle_threshold_s: float = 45.0
    db_path: str = "config/focus_index.sqlite"


class MufflingConfig(BaseModel):
    strength: float = 0.65
    break_muffling: float = 0.85
    curve_multiplier: float = 3.0


class PomodoroConfig(BaseModel):
    work_minutes: float = 25.0
    break_minutes: float = 5.0
    session_calibration_minutes: float = 5.0


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


class AdaptiveMusicConfigModel(BaseModel):
    enabled: bool = True
    intensity_smoothing: float = 0.35
    enter_focus: float = 0.40
    enter_deep_focus: float = 0.70
    leave_deep_focus: float = 0.60
    leave_focus: float = 0.30
    min_state_seconds: float = 3.0
    recovery_seconds: float = 8.0
    default_crossfade_ms: int = 1500
    master_volume: float = 0.75
    gain_slew_seconds: float = 1.0
    energy_limit: float = 2.4
    recovery_peak: float = 0.55
    layer_mix: dict[str, list[list[float]]] = Field(default_factory=dict)
    phrase_boundary_enabled: bool = True
    phrase_boundary_threshold: float = 0.40
    phrase_search_seconds: float = 10.0
    phrase_fadeout_seconds: float = 3.0
    phrase_gap_seconds: float = 0.5
    fallback_crossfade_seconds: float = 3.0


class GenerativeLayersConfig(BaseModel):
    enabled: bool = True
    api_base_url: str = "http://127.0.0.1:7862"
    model_size: str = "small"
    timeout_seconds: float = 600.0
    output_layers: list[str] = Field(default_factory=lambda: ["texture", "melody_b"])
    conda_env: str = "musicgen"
    auto_start_api: bool = True
    auto_on_upload: bool = True


class StemSeparationConfig(BaseModel):
    enabled: bool = True
    api_base_url: str = "http://127.0.0.1:7863"
    model: str = "htdemucs"
    timeout_seconds: float = 600.0
    auto_on_upload: bool = True
    # Dedicated "demucs" env is fine; lifecycle also falls back to "musicgen".
    conda_env: str = "musicgen"
    auto_start_api: bool = True


class SidecarApisConfig(BaseModel):
    startup_timeout_seconds: float = 300.0
    stop_when_done: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACS_", extra="ignore")

    app: AppConfig = Field(default_factory=AppConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    transition: TransitionConfig = Field(default_factory=TransitionConfig)
    cognitive: CognitiveConfig = Field(default_factory=CognitiveConfig)
    focus_index: FocusIndexConfigModel = Field(default_factory=FocusIndexConfigModel)
    muffling: MufflingConfig = Field(default_factory=MufflingConfig)
    pomodoro: PomodoroConfig = Field(default_factory=PomodoroConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    adaptive_music: AdaptiveMusicConfigModel = Field(
        default_factory=AdaptiveMusicConfigModel
    )
    generative_layers: GenerativeLayersConfig = Field(
        default_factory=GenerativeLayersConfig
    )
    stem_separation: StemSeparationConfig = Field(
        default_factory=StemSeparationConfig
    )
    sidecar_apis: SidecarApisConfig = Field(default_factory=SidecarApisConfig)


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

"""Persistent UI preferences (theme, colors, waveform smoothness)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def default_ui_preferences_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "user_ui_settings.json"


@dataclass
class UiPreferences:
    dark_mode: bool = True
    main_theme: str = "unknown"
    waveform_smoothness: float = 0.35
    # How strongly rising focus brightens the aurora lights (0–3).
    aurora_brightness_gain: float = 1.5
    muffling_strength: float = 0.65
    probes_enabled: bool = True
    status_colors: dict[str, str] = field(default_factory=dict)
    language: str = "en"

    def to_dict(self) -> dict[str, Any]:
        return {
            "dark_mode": bool(self.dark_mode),
            "main_theme": str(self.main_theme),
            "waveform_smoothness": float(self.waveform_smoothness),
            "aurora_brightness_gain": float(self.aurora_brightness_gain),
            "muffling_strength": float(self.muffling_strength),
            "probes_enabled": bool(self.probes_enabled),
            "status_colors": dict(self.status_colors),
            "language": str(self.language),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UiPreferences:
        prefs = cls()
        if not isinstance(data, dict):
            return prefs
        if "dark_mode" in data:
            prefs.dark_mode = bool(data["dark_mode"])
        if "main_theme" in data and data["main_theme"] is not None:
            prefs.main_theme = str(data["main_theme"])
        if "waveform_smoothness" in data:
            try:
                prefs.waveform_smoothness = float(data["waveform_smoothness"])
            except (TypeError, ValueError):
                pass
        if "aurora_brightness_gain" in data:
            try:
                prefs.aurora_brightness_gain = max(
                    0.0, min(3.0, float(data["aurora_brightness_gain"]))
                )
            except (TypeError, ValueError):
                pass
        if "muffling_strength" in data:
            try:
                prefs.muffling_strength = max(
                    0.0, min(1.0, float(data["muffling_strength"]))
                )
            except (TypeError, ValueError):
                pass
        if "probes_enabled" in data:
            prefs.probes_enabled = bool(data["probes_enabled"])
        if "language" in data and isinstance(data["language"], str):
            prefs.language = data["language"]
        colors = data.get("status_colors")
        if isinstance(colors, dict):
            prefs.status_colors = {
                str(k): str(v) for k, v in colors.items() if isinstance(v, str)
            }
        return prefs


def load_ui_preferences(path: Path | None = None) -> UiPreferences:
    target = path or default_ui_preferences_path()
    if not target.exists():
        return UiPreferences()
    try:
        with target.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return UiPreferences.from_dict(data)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load UI preferences from %s: %s", target, exc)
        return UiPreferences()


def save_ui_preferences(prefs: UiPreferences, path: Path | None = None) -> Path:
    target = path or default_ui_preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(prefs.to_dict(), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
        tmp.replace(target)
    except OSError:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
    return target

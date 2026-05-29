"""Domain events exchanged between subsystems."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class WorkContext(str, Enum):
    PROGRAMMING = "programming"
    TEAM_WORKFLOW = "team_workflow"
    READING_WRITING = "reading_writing"
    SCIENTIFIC = "scientific"
    CREATIVE_DESIGN = "creative_design"
    DISTRACTION = "distraction"
    UNKNOWN = "unknown"


class FocusState(str, Enum):
    DEEP_FOCUS = "deep_focus"
    MILD_DISTRACTION = "mild_distraction"
    OVERSTIMULATION = "overstimulation"
    FATIGUE = "fatigue"
    CALM_PRODUCTIVITY = "calm_productivity"
    FLOW = "flow"


@dataclass(frozen=True)
class ActivitySnapshot:
    """Privacy-safe activity metadata (counts and window info only)."""

    timestamp: datetime
    window_title: str
    process_name: str
    keystroke_count: int
    click_count: int
    scroll_count: int
    cpu_percent: float
    idle_seconds: float


@dataclass(frozen=True)
class ContextChanged:
    previous: WorkContext
    current: WorkContext
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class FocusUpdated:
    focus_score: float
    state: FocusState
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class AudioParametersUpdated:
    profile_id: str
    brightness: float
    energy: float
    warmth: float
    crossfade_seconds: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class ManualOverrideChanged:
    enabled: bool
    context: WorkContext | None = None
    focus_state: FocusState | None = None


@dataclass(frozen=True)
class PrivacySettingsChanged:
    collect_window_titles: bool
    collect_process_names: bool
    log_activity: bool


EventPayload = (
    ActivitySnapshot
    | ContextChanged
    | FocusUpdated
    | AudioParametersUpdated
    | ManualOverrideChanged
    | PrivacySettingsChanged
    | dict[str, Any]
)

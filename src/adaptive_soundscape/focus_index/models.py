"""Event and result models for the Focus Likelihood Index."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class AppCategory(str, Enum):
    CODE_EDITOR = "code_editor"
    TERMINAL = "terminal"
    DOCUMENT = "document"
    BROWSER_DOCS = "browser_docs"
    COMMUNICATION = "communication"
    DESIGN = "design"
    ENTERTAINMENT = "entertainment"
    SOCIAL = "social"
    OTHER = "other"


class FocusBand(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"
    UNCERTAIN = "uncertain"


class FocusStatus(str, Enum):
    OK = "ok"
    CALIBRATING = "calibrating"
    INSUFFICIENT = "insufficient"
    UNCERTAIN = "uncertain"


class FocusSource(str, Enum):
    MEASURED = "measured"
    PATTERN_SIMILARITY = "pattern_similarity"
    TIE = "tie"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppActivityEvent(BaseModel):
    event_type: Literal["app_activity"] = "app_activity"
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=_utcnow)
    app_category: AppCategory
    duration_s: float = Field(ge=0.0)
    task_profile: str = "default"
    aligned: bool = False
    calibration: bool = False

    @field_validator("timestamp")
    @classmethod
    def _ensure_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class ContextSwitchEvent(BaseModel):
    event_type: Literal["context_switch"] = "context_switch"
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=_utcnow)
    from_category: AppCategory
    to_category: AppCategory
    from_aligned: bool = False
    to_aligned: bool = False
    task_profile: str = "default"
    calibration: bool = False

    @field_validator("timestamp")
    @classmethod
    def _ensure_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class IdleStateEvent(BaseModel):
    event_type: Literal["idle_state"] = "idle_state"
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=_utcnow)
    duration_s: float = Field(ge=0.0)
    is_idle: bool = True
    task_profile: str = "default"
    calibration: bool = False

    @field_validator("timestamp")
    @classmethod
    def _ensure_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class AttentionProbeEvent(BaseModel):
    event_type: Literal["attention_probe"] = "attention_probe"
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=_utcnow)
    accuracy: float = Field(ge=0.0, le=1.0)
    omission_rate: float = Field(ge=0.0, le=1.0)
    commission_rate: float = Field(ge=0.0, le=1.0)
    rt_mean_ms: float = Field(ge=0.0)
    rt_std_ms: float = Field(ge=0.0)
    self_rating: int | None = Field(default=None, ge=1, le=7)
    task_profile: str = "default"
    calibration: bool = False

    @field_validator("timestamp")
    @classmethod
    def _ensure_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class SessionConfigEvent(BaseModel):
    event_type: Literal["session_config"] = "session_config"
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=_utcnow)
    task_profile: str = "default"
    probes_enabled: bool = True
    aligned_categories: list[str] = Field(default_factory=list)

    @field_validator("timestamp")
    @classmethod
    def _ensure_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


FocusEvent = (
    AppActivityEvent
    | ContextSwitchEvent
    | IdleStateEvent
    | AttentionProbeEvent
    | SessionConfigEvent
)


class ComponentScores(BaseModel):
    A: float | None = None
    S: float | None = None
    I: float | None = None
    P: float | None = None


class FocusIndexResult(BaseModel):
    focus_index: float | None = None
    measured_focus: float | None = None
    pattern_similarity: float | None = None
    pattern_focus: float | None = None
    focus_source: FocusSource | None = None
    focus_band: FocusBand = FocusBand.UNCERTAIN
    status: FocusStatus = FocusStatus.INSUFFICIENT
    confidence: float = 0.0
    components: ComponentScores = Field(default_factory=ComponentScores)
    task_profile: str = "default"
    window_start: datetime | None = None
    window_end: datetime | None = None
    uncertainties: list[str] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)

    def as_unit_score(self) -> float:
        """Map focus_index (0–100) to the app's 0–1 music path."""
        if self.focus_index is None:
            return 0.5
        return max(0.0, min(1.0, self.focus_index / 100.0))

"""Bridge ActivityMonitor / WorkContext into privacy-safe FLI events."""

from __future__ import annotations

from datetime import datetime, timezone

from adaptive_soundscape.core.events import ActivitySnapshot, WorkContext
from adaptive_soundscape.focus_index.models import (
    AppActivityEvent,
    AppCategory,
    ContextSwitchEvent,
    IdleStateEvent,
)

# WorkContext → FLI app category (no titles/URLs stored).
CONTEXT_TO_CATEGORY: dict[WorkContext, AppCategory] = {
    WorkContext.PROGRAMMING: AppCategory.CODE_EDITOR,
    WorkContext.TEAM_WORKFLOW: AppCategory.COMMUNICATION,
    WorkContext.READING_WRITING: AppCategory.DOCUMENT,
    WorkContext.SCIENTIFIC: AppCategory.BROWSER_DOCS,
    WorkContext.CREATIVE_DESIGN: AppCategory.DESIGN,
    WorkContext.DISTRACTION: AppCategory.ENTERTAINMENT,
    WorkContext.UNKNOWN: AppCategory.OTHER,
}

# Categories considered aligned for a given task profile (WorkContext value).
DEFAULT_ALIGNED: dict[str, set[AppCategory]] = {
    WorkContext.PROGRAMMING.value: {
        AppCategory.CODE_EDITOR,
        AppCategory.TERMINAL,
        AppCategory.BROWSER_DOCS,
    },
    WorkContext.TEAM_WORKFLOW.value: {
        AppCategory.COMMUNICATION,
        AppCategory.DOCUMENT,
    },
    WorkContext.READING_WRITING.value: {
        AppCategory.DOCUMENT,
        AppCategory.BROWSER_DOCS,
    },
    WorkContext.SCIENTIFIC.value: {
        AppCategory.BROWSER_DOCS,
        AppCategory.DOCUMENT,
        AppCategory.CODE_EDITOR,
    },
    WorkContext.CREATIVE_DESIGN.value: {
        AppCategory.DESIGN,
        AppCategory.DOCUMENT,
    },
    WorkContext.DISTRACTION.value: set(),
    WorkContext.UNKNOWN.value: {
        AppCategory.CODE_EDITOR,
        AppCategory.DOCUMENT,
        AppCategory.BROWSER_DOCS,
        AppCategory.DESIGN,
        AppCategory.TERMINAL,
    },
    "default": {
        AppCategory.CODE_EDITOR,
        AppCategory.TERMINAL,
        AppCategory.DOCUMENT,
        AppCategory.BROWSER_DOCS,
        AppCategory.DESIGN,
        AppCategory.COMMUNICATION,
    },
}


def category_for_context(context: WorkContext) -> AppCategory:
    return CONTEXT_TO_CATEGORY.get(context, AppCategory.OTHER)


def is_aligned(category: AppCategory, task_profile: str) -> bool:
    aligned = DEFAULT_ALIGNED.get(task_profile) or DEFAULT_ALIGNED["default"]
    return category in aligned


class ActivityBridge:
    """Stateful converter from poll ticks → FLI events (categories only)."""

    def __init__(
        self,
        *,
        task_profile: str = "default",
        idle_threshold_s: float = 60.0,
        calibration: bool = False,
    ) -> None:
        self.task_profile = task_profile
        self.idle_threshold_s = idle_threshold_s
        self.calibration = calibration
        self._last_category: AppCategory | None = None
        self._last_aligned: bool = False
        self._was_idle: bool = False

    def set_task_profile(self, task_profile: str) -> None:
        self.task_profile = task_profile

    def set_calibration(self, enabled: bool) -> None:
        self.calibration = enabled

    def ingest(
        self,
        snapshot: ActivitySnapshot,
        context: WorkContext,
        *,
        interval_s: float,
        force_aligned: bool = False,
    ) -> list:
        """Return zero or more FLI events for this tick. Never stores titles."""
        now = snapshot.timestamp
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        category = category_for_context(context)
        aligned = True if force_aligned else is_aligned(category, self.task_profile)
        events: list = []

        idle = float(snapshot.idle_seconds) >= self.idle_threshold_s
        if idle:
            if not self._was_idle:
                events.append(
                    IdleStateEvent(
                        timestamp=now,
                        duration_s=max(interval_s, float(snapshot.idle_seconds)),
                        is_idle=True,
                        task_profile=self.task_profile,
                        calibration=self.calibration,
                    )
                )
            self._was_idle = True
        else:
            if self._was_idle:
                events.append(
                    IdleStateEvent(
                        timestamp=now,
                        duration_s=interval_s,
                        is_idle=False,
                        task_profile=self.task_profile,
                        calibration=self.calibration,
                    )
                )
            self._was_idle = False
            events.append(
                AppActivityEvent(
                    timestamp=now,
                    app_category=category,
                    duration_s=max(0.0, interval_s),
                    task_profile=self.task_profile,
                    aligned=aligned,
                    calibration=self.calibration,
                )
            )

        if self._last_category is not None and category != self._last_category:
            events.append(
                ContextSwitchEvent(
                    timestamp=now,
                    from_category=self._last_category,
                    to_category=category,
                    from_aligned=self._last_aligned,
                    to_aligned=aligned,
                    task_profile=self.task_profile,
                    calibration=self.calibration,
                )
            )
        self._last_category = category
        self._last_aligned = aligned
        return events

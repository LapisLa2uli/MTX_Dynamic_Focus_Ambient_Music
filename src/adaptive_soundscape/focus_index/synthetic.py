"""Synthetic event generators for demos and tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from adaptive_soundscape.focus_index.models import (
    AppActivityEvent,
    AppCategory,
    AttentionProbeEvent,
    ContextSwitchEvent,
    FocusEvent,
    IdleStateEvent,
)


def _t0() -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def aligned_session(minutes: int = 10, profile: str = "programming") -> list[FocusEvent]:
    start = _t0()
    events: list[FocusEvent] = []
    for i in range(minutes):
        ts = start + timedelta(minutes=i)
        events.append(
            AppActivityEvent(
                timestamp=ts,
                app_category=AppCategory.CODE_EDITOR,
                duration_s=55.0,
                task_profile=profile,
                aligned=True,
            )
        )
        if i % 4 == 3:
            events.append(
                ContextSwitchEvent(
                    timestamp=ts + timedelta(seconds=55),
                    from_category=AppCategory.CODE_EDITOR,
                    to_category=AppCategory.TERMINAL,
                    from_aligned=True,
                    to_aligned=True,
                    task_profile=profile,
                )
            )
            events.append(
                AppActivityEvent(
                    timestamp=ts + timedelta(seconds=56),
                    app_category=AppCategory.TERMINAL,
                    duration_s=4.0,
                    task_profile=profile,
                    aligned=True,
                )
            )
    events.append(
        AttentionProbeEvent(
            timestamp=start + timedelta(minutes=minutes),
            accuracy=0.92,
            omission_rate=0.05,
            commission_rate=0.03,
            rt_mean_ms=320.0,
            rt_std_ms=40.0,
            task_profile=profile,
        )
    )
    return events


def distracting_session(minutes: int = 10, profile: str = "programming") -> list[FocusEvent]:
    start = _t0()
    events: list[FocusEvent] = []
    cats = [
        AppCategory.ENTERTAINMENT,
        AppCategory.SOCIAL,
        AppCategory.CODE_EDITOR,
        AppCategory.COMMUNICATION,
    ]
    prev = cats[0]
    for i in range(minutes * 3):
        ts = start + timedelta(seconds=20 * i)
        cat = cats[i % len(cats)]
        aligned = cat in (AppCategory.CODE_EDITOR, AppCategory.TERMINAL)
        events.append(
            AppActivityEvent(
                timestamp=ts,
                app_category=cat,
                duration_s=18.0,
                task_profile=profile,
                aligned=aligned,
            )
        )
        if cat != prev:
            events.append(
                ContextSwitchEvent(
                    timestamp=ts,
                    from_category=prev,
                    to_category=cat,
                    from_aligned=prev in (AppCategory.CODE_EDITOR, AppCategory.TERMINAL),
                    to_aligned=aligned,
                    task_profile=profile,
                )
            )
        prev = cat
    return events


def idle_heavy_session(minutes: int = 10, profile: str = "programming") -> list[FocusEvent]:
    start = _t0()
    return [
        AppActivityEvent(
            timestamp=start,
            app_category=AppCategory.CODE_EDITOR,
            duration_s=30.0,
            task_profile=profile,
            aligned=True,
        ),
        IdleStateEvent(
            timestamp=start + timedelta(seconds=30),
            duration_s=float(minutes * 60 - 30),
            is_idle=True,
            task_profile=profile,
        ),
    ]


def no_activity(profile: str = "programming") -> list[FocusEvent]:
    return []

"""Transition controller with crossfade timing and hysteresis."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from adaptive_soundscape.audio.parameters import AudioParameters
from adaptive_soundscape.audio.profiles import adapt_parameters, profile_for_context
from adaptive_soundscape.core.events import FocusState, WorkContext


@dataclass
class TransitionDecision:
    profile_id: str
    display_name: str
    parameters: AudioParameters
    crossfade_seconds: float
    should_transition: bool


@dataclass
class TransitionController:
    """Manage gradual audio transitions with cooldown and hysteresis."""

    deep_focus_crossfade_seconds: float = 12.0
    distraction_recovery_seconds: float = 4.5
    cooldown_seconds: float = 60.0
    hysteresis_threshold: float = 0.08
    _active_profile: str = "unknown"
    _active_context: WorkContext = WorkContext.UNKNOWN
    _active_state: FocusState = FocusState.CALM_PRODUCTIVITY
    _last_transition: float = field(default_factory=lambda: 0.0)
    _pending_params: AudioParameters | None = None

    def decide(
        self,
        context: WorkContext,
        focus_state: FocusState,
        focus_score: float,
    ) -> TransitionDecision:
        profile = profile_for_context(context)
        params = adapt_parameters(profile, focus_state)
        now = time.monotonic()

        profile_changed = profile.profile_id != self._active_profile
        state_changed = focus_state != self._active_state
        score_delta = abs(focus_score - getattr(self, "_last_score", focus_score))
        self._last_score = focus_score  # type: ignore[attr-defined]

        in_cooldown = (now - self._last_transition) < self.cooldown_seconds
        minor_change = (
            not profile_changed
            and state_changed
            and score_delta < self.hysteresis_threshold
        )

        should = profile_changed or (
            state_changed and not minor_change and not in_cooldown
        )

        if focus_state in (FocusState.DEEP_FOCUS, FocusState.FLOW) and not profile_changed:
            # minimize changes during deep focus
            params = adapt_parameters(profile_for_context(self._active_context), self._active_state)
            should = profile_changed

        crossfade = self.deep_focus_crossfade_seconds
        if focus_state == FocusState.MILD_DISTRACTION or context == WorkContext.DISTRACTION:
            crossfade = self.distraction_recovery_seconds
        elif profile_changed:
            crossfade = (self.deep_focus_crossfade_seconds + self.distraction_recovery_seconds) / 2.0

        if should:
            self._active_profile = profile.profile_id
            self._active_context = context
            self._active_state = focus_state
            self._last_transition = now
            self._pending_params = params

        return TransitionDecision(
            profile_id=profile.profile_id,
            display_name=profile.display_name,
            parameters=params if should else (self._pending_params or params),
            crossfade_seconds=crossfade,
            should_transition=should,
        )

    def force_profile(self, context: WorkContext, state: FocusState) -> TransitionDecision:
        profile = profile_for_context(context)
        params = adapt_parameters(profile, state)
        self._active_profile = profile.profile_id
        self._active_context = context
        self._active_state = state
        self._last_transition = time.monotonic()
        self._pending_params = params
        return TransitionDecision(
            profile_id=profile.profile_id,
            display_name=profile.display_name,
            parameters=params,
            crossfade_seconds=self.distraction_recovery_seconds,
            should_transition=True,
        )

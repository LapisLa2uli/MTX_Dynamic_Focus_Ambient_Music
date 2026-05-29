"""Context and focus-state audio profiles."""

from __future__ import annotations

from dataclasses import dataclass

from adaptive_soundscape.audio.parameters import AudioParameters
from adaptive_soundscape.core.events import FocusState, WorkContext


@dataclass(frozen=True)
class AudioProfile:
    profile_id: str
    display_name: str
    base: AudioParameters


CONTEXT_PROFILES: dict[WorkContext, AudioProfile] = {
    WorkContext.PROGRAMMING: AudioProfile(
        "programming", "Deep Code", AudioParameters(0.45, 0.35, 0.55)
    ),
    WorkContext.TEAM_WORKFLOW: AudioProfile(
        "team_workflow", "Collaborative", AudioParameters(0.55, 0.50, 0.60)
    ),
    WorkContext.READING_WRITING: AudioProfile(
        "reading_writing", "Quiet Study", AudioParameters(0.40, 0.25, 0.65)
    ),
    WorkContext.SCIENTIFIC: AudioProfile(
        "scientific", "Lab Focus", AudioParameters(0.50, 0.40, 0.50)
    ),
    WorkContext.CREATIVE_DESIGN: AudioProfile(
        "creative_design", "Creative Flow", AudioParameters(0.65, 0.55, 0.55)
    ),
    WorkContext.DISTRACTION: AudioProfile(
        "distraction", "Recovery", AudioParameters(0.35, 0.30, 0.70)
    ),
    WorkContext.UNKNOWN: AudioProfile(
        "unknown", "Neutral", AudioParameters(0.50, 0.40, 0.55)
    ),
}


def adapt_parameters(profile: AudioProfile, state: FocusState) -> AudioParameters:
    """Adapt brightness/energy/warmth based on cognitive state."""
    p = profile.base
    if state == FocusState.DEEP_FOCUS or state == FocusState.FLOW:
        return p  # minimize changes
    if state == FocusState.OVERSTIMULATION:
        return AudioParameters(
            brightness=p.brightness * 0.75,
            energy=p.energy * 0.65,
            warmth=p.warmth,
        )
    if state == FocusState.FATIGUE:
        return AudioParameters(
            brightness=p.brightness * 0.90,
            energy=p.energy * 0.80,
            warmth=min(1.0, p.warmth + 0.15),
        )
    if state == FocusState.MILD_DISTRACTION:
        return AudioParameters(
            brightness=p.brightness * 0.85,
            energy=p.energy * 0.75,
            warmth=min(1.0, p.warmth + 0.08),
        )
    return p


def profile_for_context(context: WorkContext) -> AudioProfile:
    return CONTEXT_PROFILES.get(context, CONTEXT_PROFILES[WorkContext.UNKNOWN])

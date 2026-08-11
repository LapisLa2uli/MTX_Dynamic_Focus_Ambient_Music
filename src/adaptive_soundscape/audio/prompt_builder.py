"""Deterministic prompt templates for MusicGen intensity-layer generation."""

from __future__ import annotations

from dataclasses import dataclass


NEGATIVE_PROMPT = (
    "vocals, singing, speech, talking, rap, lyrics, voiceover, "
    "harsh distortion, sirens, sudden drops, glitch noise, crowd noise"
)

_SCENARIO_STYLE: dict[str, str] = {
    "programming": "calm programming focus ambient, soft synth pads, gentle",
    "scientific": "analytical focus ambient, clean tones, spacious",
    "reading_writing": "quiet reading atmosphere, warm soft instruments",
    "creative_design": "creative ambient, airy textures, light melodic hints",
    "team_workflow": "steady collaborative ambient, soft pulse, unobtrusive",
    "distraction": "soothing recovery ambient, warm low energy",
    "unknown": "neutral focus ambient, soft instrumental",
}

_LAYER_HINTS: dict[str, str] = {
    "texture": (
        "sparse high-frequency texture layer, soft granular sparkle, "
        "no drums, low melodic density, loopable detail bed"
    ),
    "melody_b": (
        "soft instrumental countermelody, modal and gentle, sits under a main motif, "
        "minimal rhythm, no lead aggression, loopable"
    ),
    "harmony": "soft harmonic pad layer, sustained chords, no percussion",
    "melody_a": "simple soft melodic motif, instrumental, loopable",
    "rhythm": "very soft muted pulse, minimal percussion, low energy",
    "pad": "deep warm pad bed, seamless loop, no melody",
    "recovery": "warm sparse recovery texture, gentle and quiet",
}


@dataclass(frozen=True)
class BuiltPrompt:
    prompt: str
    negative_prompt: str
    intensity_band: str


def intensity_band_for_layer(layer_id: str) -> str:
    if layer_id in {"melody_b", "texture"}:
        return "high"
    if layer_id in {"melody_a", "harmony"}:
        return "mid"
    return "low"


def build_layer_prompt(
    *,
    scenario: str,
    layer_id: str,
    bpm: float,
    loop_seconds: float,
    bars_per_loop: int = 8,
) -> BuiltPrompt:
    style = _SCENARIO_STYLE.get(scenario, _SCENARIO_STYLE["unknown"])
    hint = _LAYER_HINTS.get(layer_id, "soft instrumental ambient layer, loopable")
    band = intensity_band_for_layer(layer_id)
    prompt = (
        f"{style}; {hint}; {bpm:.0f} BPM; {bars_per_loop} bars; "
        f"exactly loopable {loop_seconds:.2f} seconds; "
        f"instrumental only; seamless loop; studio quality; intensity={band}"
    )
    return BuiltPrompt(
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        intensity_band=band,
    )

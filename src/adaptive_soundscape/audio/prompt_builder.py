"""Deterministic prompt templates for MusicGen intensity-layer generation."""

from __future__ import annotations

from dataclasses import dataclass


NEGATIVE_PROMPT = (
    "vocals, singing, speech, talking, rap, lyrics, voiceover, "
    "harsh distortion, sirens, sudden drops, glitch noise, crowd noise, "
    "EDM drop, heavy kick, trap hi-hats, solo piano virtuosity"
)

_SCENARIO_STYLE: dict[str, str] = {
    "programming": "calm programming focus ambient, soft synth pads, gentle low melody density",
    "scientific": "analytical focus ambient, clean sparse tones, spacious quiet room",
    "reading_writing": "quiet reading atmosphere, warm soft instruments, bookish calm",
    "creative_design": "creative ambient, airy textures, light melodic hints, soft colour",
    "team_workflow": "steady collaborative ambient, soft pulse, unobtrusive office calm",
    "distraction": "soothing recovery ambient, warm low energy, gentle reset bed",
    "unknown": "neutral focus ambient, soft instrumental, understated",
}

_LAYER_HINTS: dict[str, str] = {
    "texture": (
        "sparse high-frequency texture layer, soft granular sparkle, "
        "absolutely no kick or snare, low melodic density, loopable detail bed"
    ),
    "melody_b": (
        "single soft mid-register motif, modal and gentle, sits under a main line, "
        "minimal rhythm, no lead aggression, loopable"
    ),
    "harmony": "soft harmonic pad layer, sustained chords, no percussion",
    "melody_a": "simple soft melodic motif, instrumental, loopable",
    "rhythm": "very soft muted pulse, minimal percussion, low energy",
    "pad": "deep warm pad bed, seamless loop, no melody",
    "recovery": "warm sparse recovery texture, gentle and quiet",
}


_SONG_MIX_HINT = (
    "complete instrumental focus mix, balanced full arrangement, "
    "soft pad bed with light harmony and a gentle motif, "
    "minimal soft pulse, no vocals, seamless loop"
)


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


def build_song_prompt(
    *,
    scenario: str,
    variant_index: int = 0,
    bpm: float = 70.0,
    loop_seconds: float = 27.428,
    bars_per_loop: int = 8,
) -> BuiltPrompt:
    """Full-mix prompt for generating a new album song seed via MusicGen."""
    style = _SCENARIO_STYLE.get(scenario, _SCENARIO_STYLE["unknown"])
    variant = f"variation {variant_index + 1}, distinct motif from other album tracks"
    prompt = (
        f"{style}; {_SONG_MIX_HINT}; {variant}; {bpm:.0f} BPM; "
        f"{bars_per_loop} bars; exactly loopable {loop_seconds:.2f} seconds; "
        f"instrumental only; seamless loop; studio quality"
    )
    return BuiltPrompt(
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        intensity_band="mid",
    )

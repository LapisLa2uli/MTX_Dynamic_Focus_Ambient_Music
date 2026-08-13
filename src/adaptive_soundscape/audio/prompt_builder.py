"""Deterministic prompt templates for MusicGen intensity-layer generation."""

from __future__ import annotations

from dataclasses import dataclass


NEGATIVE_PROMPT = (
    "vocals, singing, speech, talking, rap, lyrics, voiceover, "
    "harsh distortion, sirens, sudden drops, glitch noise, crowd noise, "
    "EDM drop, heavy kick, trap hi-hats, solo piano virtuosity, "
    "fast hi-hats, aggressive basslines, cinematic trailer drums, "
    "emotional orchestral swells, rapid sequencing, bright lead synths, "
    "frantic pacing, bright cymbals, heroic themes, dense layering"
)

_UNIVERSAL = (
    "low dynamic contrast, smooth compression, muffled filtered percussion, "
    "sustained textures over rhythmic density, slow pacing, wide negative space, "
    "gradual layering, no sudden transitions, no bright transients, "
    "no attention-grabbing melodic hooks, instrumental only, seamless loop"
)

# Full-mix briefs from Focus Music Requirements (compressed for MusicGen).
_SCENARIO_SONG: dict[str, tuple[float, str]] = {
    "programming": (
        70.0,
        "slow-paced instrumental focus music for programming and engineering; "
        "ambient minimal techno with restrained futuristic electronic production; "
        "70 BPM quarter-note pulse, genuinely slow and deliberate; "
        "warm analog synth pads, low sustained bass drones, "
        "muted techno kick drums with heavy muffling, sparse low-volume percussion, "
        "subtle mechanical clicking textures, restrained synth pulses, "
        "distant electronic ambience, soft filtered arpeggiator fragments, "
        "tape hiss and room ambience; percussion deeply buried with soft attack "
        "and minimal high frequencies; wide rhythmic spacing; slow harmonic movement; "
        "minimal repetitive melody; late-night calm engineering atmosphere",
    ),
    "team_workflow": (
        76.0,
        "slow-paced productivity music with restrained tension and controlled momentum; "
        "minimal ambient electronic with soft techno influences; "
        "76 BPM quarter-note pulse, slow and grounded; "
        "muted kick drums, soft low percussion, warm bass pulses, "
        "subtle industrial textures, restrained synth ostinatos, soft analog pads, "
        "quiet ticking percussion, low atmospheric drones, lightly filtered electronics; "
        "percussion heavily muffled and deep in the background; "
        "repeating rhythmic fragments with wide spacing; gradual textural evolution; "
        "calm organized late-night coordinated team workflow, not panicked",
    ),
    "reading_writing": (
        62.0,
        "slow-paced instrumental focus music for reading in a warm coffee shop; "
        "ambient jazz, soft blues, restrained lo-fi production; "
        "62 BPM quarter-note pulse, relaxed and spacious; "
        "soft tenor saxophone phrases, brushed jazz drums with heavy muffling, "
        "sparse upright bass, warm electric piano chords, soft Rhodes piano, "
        "subtle vinyl crackle, low cafe ambience, gentle room reverb, "
        "quiet sustained ambient pads; saxophone slow, sparse, understated; "
        "percussion quiet and blended; long pauses between phrases; "
        "quiet jazz band in the corner of a cafe while someone reads",
    ),
    "scientific": (
        68.0,
        "slow-paced instrumental music for scientific and mathematical work; "
        "ambient orchestral-electronic hybrid with restrained minimal techno; "
        "68 BPM quarter-note pulse, slow, heavy, deliberate; "
        "deep sustained string drones, soft low piano notes, "
        "restrained analog synth textures, subtle pulsing bass tones, "
        "distant orchestral ambience, low filtered percussion, "
        "sparse mechanical rhythmic pulses, soft granular textures, "
        "minimal brass swells at extremely low volume; "
        "percussion muffled and secondary; slow harmonic progression; "
        "minimal unresolved melodies; quiet blackboard problem-solving at night",
    ),
    "creative_design": (
        72.0,
        "slow-paced instrumental focus music for collaborative design sessions; "
        "warm ambient electronic with restrained organic textures; "
        "72 BPM quarter-note pulse, slow and steady; "
        "warm synth pads, soft plucked electronic textures, muted low percussion, "
        "brushed rhythmic elements, subtle bass pulses, soft electric piano chords, "
        "restrained guitar ambience, low vinyl texture, gentle room ambience, "
        "sparse electronic pulse fragments; muffled soft percussion; "
        "gradual evolution with repeating textures; short understated melodic phrases; "
        "warm late-night creative meeting over coffee",
    ),
    "distraction": (
        58.0,
        "soothing recovery ambient for a brief mental reset; "
        "warm low energy pads, almost no percussion, gentle drones, "
        "soft tape hiss, very slow harmonic movement; 58 BPM; "
        "quiet and spacious, no melody hooks",
    ),
    "unknown": (
        66.0,
        "neutral focus ambient, soft instrumental, understated pads and quiet pulse; "
        "66 BPM; spacious negative space, muffled percussion, studio quality",
    ),
}

_SCENARIO_STYLE: dict[str, str] = {
    key: text.split(";")[0] for key, (_bpm, text) in _SCENARIO_SONG.items()
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
    "rhythm": "very soft muted pulse, minimal percussion, low energy, heavy muffling",
    "pad": "deep warm pad bed, seamless loop, no melody",
    "recovery": "warm sparse recovery texture, gentle and quiet",
}


@dataclass(frozen=True)
class BuiltPrompt:
    prompt: str
    negative_prompt: str
    intensity_band: str
    bpm: float = 70.0


def intensity_band_for_layer(layer_id: str) -> str:
    if layer_id in {"melody_b", "texture"}:
        return "high"
    if layer_id in {"melody_a", "harmony"}:
        return "mid"
    return "low"


def scenario_bpm(scenario: str, default: float = 70.0) -> float:
    entry = _SCENARIO_SONG.get(scenario)
    return float(entry[0]) if entry else default


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
        f"{_UNIVERSAL}; intensity={band}"
    )
    return BuiltPrompt(
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        intensity_band=band,
        bpm=bpm,
    )


def build_song_prompt(
    *,
    scenario: str,
    variant_index: int = 0,
    bpm: float | None = None,
    loop_seconds: float = 27.428,
    bars_per_loop: int = 8,
) -> BuiltPrompt:
    """Full-mix prompt for generating a new album song seed via MusicGen."""
    entry = _SCENARIO_SONG.get(scenario, _SCENARIO_SONG["unknown"])
    default_bpm, body = entry
    use_bpm = float(bpm) if bpm is not None else default_bpm
    variant = f"variation {variant_index + 1}, distinct motif from other album tracks"
    prompt = (
        f"{body}; {variant}; {use_bpm:.0f} BPM; {bars_per_loop} bars; "
        f"exactly loopable {loop_seconds:.2f} seconds; {_UNIVERSAL}"
    )
    return BuiltPrompt(
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        intensity_band="mid",
        bpm=use_bpm,
    )

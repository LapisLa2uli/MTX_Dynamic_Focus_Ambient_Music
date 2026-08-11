"""Snapshot-style tests for MusicGen prompt builder."""

from adaptive_soundscape.audio.prompt_builder import NEGATIVE_PROMPT, build_layer_prompt


def test_texture_prompt_contains_constraints():
    built = build_layer_prompt(
        scenario="programming",
        layer_id="texture",
        bpm=70,
        loop_seconds=27.428,
    )
    assert "70 BPM" in built.prompt
    assert "27.43" in built.prompt or "27.428" in built.prompt
    assert "texture" in built.prompt.lower() or "sparkle" in built.prompt.lower()
    assert built.intensity_band == "high"
    assert "vocals" in built.negative_prompt
    assert built.negative_prompt == NEGATIVE_PROMPT


def test_prompt_deterministic():
    a = build_layer_prompt(
        scenario="scientific", layer_id="melody_b", bpm=72, loop_seconds=30.0
    )
    b = build_layer_prompt(
        scenario="scientific", layer_id="melody_b", bpm=72, loop_seconds=30.0
    )
    assert a == b

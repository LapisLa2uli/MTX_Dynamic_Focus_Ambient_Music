"""Tests for audio asset generation."""

from adaptive_soundscape.audio.asset_generator import generate_pads, generate_mains


def test_generate_pads_creates_missing_files(tmp_path):
    from adaptive_soundscape.audio.asset_generator import _render_pad, write_wav

    write_wav(tmp_path / "programming.wav", _render_pad(110, 220, 0.08, 1.0))
    written = generate_pads(tmp_path)
    assert len(written) == 1
    assert (tmp_path / "programming_pad.wav").exists()


def test_generate_pads_skips_existing(tmp_path):
    from adaptive_soundscape.audio.asset_generator import _render_pad, write_wav

    write_wav(tmp_path / "programming.wav", _render_pad(110, 220, 0.08, 1.0))
    generate_pads(tmp_path)
    second = generate_pads(tmp_path)
    assert second == []


def test_generate_mains_and_pads_together(tmp_path):
    generate_mains(tmp_path)
    generate_pads(tmp_path)
    assert (tmp_path / "scientific.wav").exists()
    assert (tmp_path / "scientific_pad.wav").exists()

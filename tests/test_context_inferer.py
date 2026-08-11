"""Tests for unknown-window inference and user mappings."""

from datetime import datetime, timezone
from pathlib import Path

from adaptive_soundscape.context.classifier import classify_snapshot, resolve_context
from adaptive_soundscape.context.inferer import ContextInferer
from adaptive_soundscape.context.user_mappings import (
    UserMappings,
    load_user_mappings,
    save_user_mappings,
)
from adaptive_soundscape.core.events import ActivitySnapshot, WorkContext


def _snapshot(title: str, process: str) -> ActivitySnapshot:
    return ActivitySnapshot(
        timestamp=datetime.now(timezone.utc),
        window_title=title,
        process_name=process,
        keystroke_count=0,
        click_count=0,
        scroll_count=0,
        cpu_percent=10.0,
        idle_seconds=0.0,
    )


def test_inferer_guesses_programming_from_seed_app():
    inferer = ContextInferer()
    result = inferer.infer("zed.exe", "main.rs — Zed")
    assert result.context == WorkContext.PROGRAMMING
    assert result.confidence >= 0.4


def test_inferer_guesses_distraction_from_seed():
    inferer = ContextInferer()
    result = inferer.infer("chrome.exe", "Funny clips - Bilibili")
    assert result.context == WorkContext.DISTRACTION


def test_resolve_uses_user_mapping_without_confirm():
    mappings = UserMappings()
    mappings.add_process(WorkContext.CREATIVE_DESIGN, "mydesignapp")
    resolved = resolve_context(
        _snapshot("Project Board", "mydesignapp.exe"),
        user_mappings=mappings,
    )
    assert resolved.context == WorkContext.CREATIVE_DESIGN
    assert resolved.source == "user"
    assert resolved.is_misc is False
    assert resolved.needs_confirm is False


def test_user_process_mapping_overrides_builtin_rules():
    """Saved toast choices must stick even when built-ins prefer another category."""
    mappings = UserMappings()
    mappings.add_process(WorkContext.CREATIVE_DESIGN, "chrome")
    resolved = resolve_context(
        _snapshot("Funny clips - YouTube", "chrome.exe"),
        user_mappings=mappings,
    )
    assert resolved.context == WorkContext.CREATIVE_DESIGN
    assert resolved.source == "user"
    assert resolved.needs_confirm is False


def test_resolve_misc_needs_confirm_when_unknown_to_rules():
    # A made-up process should not match DEFAULT_RULES.
    builtin = classify_snapshot(_snapshot("Strange Tool", "qzxtool999.exe"))
    assert builtin.context == WorkContext.UNKNOWN

    resolved = resolve_context(_snapshot("Strange Tool", "qzxtool999.exe"))
    assert resolved.is_misc is True
    assert resolved.needs_confirm is True


def test_user_mappings_roundtrip(tmp_path: Path):
    path = tmp_path / "mappings.json"
    mappings = UserMappings()
    mappings.add_process(WorkContext.SCIENTIFIC, "rstudio")
    mappings.add_title_keyword(WorkContext.SCIENTIFIC, "hypothesis")
    save_user_mappings(mappings, path)

    loaded = load_user_mappings(path)
    assert "rstudio" in loaded.get(WorkContext.SCIENTIFIC).process_names
    assert "hypothesis" in loaded.get(WorkContext.SCIENTIFIC).title_keywords
    rules = loaded.to_rules()
    assert any(rule.context == WorkContext.SCIENTIFIC for rule in rules)


def test_add_process_moves_between_categories():
    mappings = UserMappings()
    mappings.add_process(WorkContext.PROGRAMMING, "sharedapp")
    mappings.add_process(WorkContext.READING_WRITING, "sharedapp")
    assert "sharedapp" not in mappings.get(WorkContext.PROGRAMMING).process_names
    assert "sharedapp" in mappings.get(WorkContext.READING_WRITING).process_names

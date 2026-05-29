"""Rule-based context classification patterns."""

from __future__ import annotations

from dataclasses import dataclass

from adaptive_soundscape.core.events import WorkContext


@dataclass(frozen=True)
class ContextRule:
    context: WorkContext
    process_names: tuple[str, ...] = ()
    title_keywords: tuple[str, ...] = ()
    weight: float = 1.0


DEFAULT_RULES: tuple[ContextRule, ...] = (
    ContextRule(
        WorkContext.PROGRAMMING,
        process_names=("code.exe", "devenv.exe", "cursor.exe", "pycharm64.exe", "idea64.exe"),
        title_keywords=("visual studio", "vscode", "cursor", "python", "javascript", "git"),
        weight=1.2,
    ),
    ContextRule(
        WorkContext.TEAM_WORKFLOW,
        process_names=("teams.exe", "slack.exe", "zoom.exe", "outlook.exe", "discord.exe"),
        title_keywords=("teams", "slack", "zoom", "meet", "calendar", "mail"),
        weight=1.0,
    ),
    ContextRule(
        WorkContext.READING_WRITING,
        process_names=("winword.exe", "notepad.exe", "notion.exe", "obsidian.exe"),
        title_keywords=("word", "notion", "obsidian", "document", "notes", "read"),
        weight=1.0,
    ),
    ContextRule(
        WorkContext.SCIENTIFIC,
        process_names=("matlab.exe", "wolfram", "jupyter"),
        title_keywords=("jupyter", "matlab", "lab", "research", "arxiv", "dataset"),
        weight=1.1,
    ),
    ContextRule(
        WorkContext.CREATIVE_DESIGN,
        process_names=("figma.exe", "photoshop.exe", "blender.exe", "illustrator.exe"),
        title_keywords=("figma", "photoshop", "design", "blender", "illustrator", "canvas"),
        weight=1.0,
    ),
    ContextRule(
        WorkContext.DISTRACTION,
        process_names=("chrome.exe", "msedge.exe", "firefox.exe", "spotify.exe"),
        title_keywords=("youtube", "twitter", "reddit", "facebook", "instagram", "tiktok", "game"),
        weight=0.9,
    ),
)

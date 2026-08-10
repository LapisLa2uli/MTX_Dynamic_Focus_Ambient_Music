"""Lightweight inference for windows that miss the built-in rule dictionary."""

from __future__ import annotations

import re
from dataclasses import dataclass

from adaptive_soundscape.context.rules import DEFAULT_RULES
from adaptive_soundscape.context.user_mappings import UserMappings
from adaptive_soundscape.core.events import WorkContext

# Common apps not always covered by DEFAULT_RULES; used only as soft priors.
SEED_LEXICON: dict[WorkContext, tuple[str, ...]] = {
    WorkContext.PROGRAMMING: (
        "zed",
        "warp",
        "alacritty",
        "wezterm",
        "kitty",
        "helix",
        "gitkraken",
        "sourcetree",
        "fork",
        "postman",
        "insomnia",
        "docker",
        "dbeaver",
        "tableplus",
        "vscode",
        "code",
        "terminal",
        "shell",
        "compiler",
        "debugger",
        "repository",
        "commit",
        "branch",
        "pull",
        "merge",
        "stack",
        "traceback",
        "pytest",
        "unittest",
    ),
    WorkContext.TEAM_WORKFLOW: (
        "telegram",
        "whatsapp",
        "skype",
        "mattermost",
        "rocket",
        "feishu",
        "lark",
        "dingtalk",
        "wechat",
        "meeting",
        "standup",
        "sprint",
        "kanban",
        "asana",
        "trello",
        "linear",
        "monday",
        "clickup",
        "calendar",
        "inbox",
        "email",
        "mail",
    ),
    WorkContext.READING_WRITING: (
        "word",
        "pages",
        "scrivener",
        "typora",
        "craft",
        "bear",
        "ulysses",
        "evernote",
        "onenote",
        "docs",
        "google docs",
        "overleaf",
        "latex",
        "markdown",
        "notes",
        "journal",
        "essay",
        "draft",
        "chapter",
        "writing",
    ),
    WorkContext.SCIENTIFIC: (
        "rstudio",
        "mathematica",
        "maple",
        "origin",
        "labview",
        "comsol",
        "ansys",
        "octave",
        "sage",
        "hypothesis",
        "experiment",
        "simulation",
        "analysis",
        "statistics",
        "equation",
        "formula",
        "thesis",
        "paper",
        "citation",
        "bibtex",
    ),
    WorkContext.CREATIVE_DESIGN: (
        "sketch",
        "affinity",
        "canva",
        "krita",
        "gimp",
        "inkscape",
        "procreate",
        "cinema4d",
        "maya",
        "houdini",
        "substance",
        "unity",
        "unreal",
        "godot",
        "storyboard",
        "prototype",
        "wireframe",
        "illustration",
        "animation",
        "render",
    ),
    WorkContext.DISTRACTION: (
        "bilibili",
        "douyin",
        "weibo",
        "hulu",
        "disney",
        "prime video",
        "iqiyi",
        "youku",
        "steam",
        "epic",
        "origin",
        "battlenet",
        "xbox",
        "playstation",
        "meme",
        "shorts",
        "reels",
        "viral",
        "entertainment",
        "shopping",
        "amazon",
        "taobao",
    ),
}


@dataclass(frozen=True)
class InferenceResult:
    context: WorkContext
    confidence: float
    scores: dict[WorkContext, float]
    source: str  # "seed" | "similarity" | "none"


class ContextInferer:
    """Score unknown windows via seed lexicon + token overlap with known labels."""

    def __init__(self, user_mappings: UserMappings | None = None) -> None:
        self._user_mappings = user_mappings or UserMappings()
        self._lexicon = self._build_lexicon()

    def set_user_mappings(self, mappings: UserMappings) -> None:
        self._user_mappings = mappings
        self._lexicon = self._build_lexicon()

    def infer(self, process_name: str, window_title: str) -> InferenceResult:
        process = _normalize(process_name)
        title = _normalize(window_title)
        if not process and not title:
            return InferenceResult(WorkContext.UNKNOWN, 0.0, {}, "none")

        tokens = _tokenize(f"{process} {title}")
        scores: dict[WorkContext, float] = {
            ctx: 0.0 for ctx in WorkContext if ctx != WorkContext.UNKNOWN
        }

        for ctx, lexicon in self._lexicon.items():
            seed_hit = _best_substring_hit(process, title, lexicon)
            if seed_hit > 0:
                scores[ctx] = max(scores[ctx], 0.55 + 0.35 * seed_hit)

            overlap = tokens & lexicon
            if overlap:
                # Prefer denser overlap without requiring huge titles.
                ratio = len(overlap) / max(min(len(tokens), 8), 1)
                scores[ctx] = max(scores[ctx], min(0.82, 0.35 + 0.55 * ratio))

        if not any(scores.values()):
            return InferenceResult(WorkContext.UNKNOWN, 0.0, scores, "none")

        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        confidence = scores[best]
        # Softmax-ish margin: require a clear winner.
        runner_up = max((v for k, v in scores.items() if k != best), default=0.0)
        if confidence < 0.40 or confidence - runner_up < 0.08:
            return InferenceResult(WorkContext.UNKNOWN, confidence, scores, "none")

        source = "seed" if confidence >= 0.55 else "similarity"
        return InferenceResult(best, min(0.88, confidence), scores, source)

    def _build_lexicon(self) -> dict[WorkContext, set[str]]:
        lexicon: dict[WorkContext, set[str]] = {
            ctx: set() for ctx in WorkContext if ctx != WorkContext.UNKNOWN
        }
        for rule in DEFAULT_RULES:
            lexicon[rule.context].update(_tokenize(" ".join(rule.process_names)))
            lexicon[rule.context].update(_tokenize(" ".join(rule.title_keywords)))
        for ctx, words in SEED_LEXICON.items():
            lexicon[ctx].update(_tokenize(" ".join(words)))
        for ctx, mapping in self._user_mappings.by_context.items():
            if ctx == WorkContext.UNKNOWN:
                continue
            lexicon[ctx].update(_tokenize(" ".join(mapping.process_names)))
            lexicon[ctx].update(_tokenize(" ".join(mapping.title_keywords)))
        # Drop ultra-generic tokens that pollute every class.
        stop = {"app", "window", "microsoft", "google", "exe", "new", "untitled"}
        for ctx in lexicon:
            lexicon[ctx] -= stop
        return lexicon


def _normalize(text: str) -> str:
    value = text.lower().strip()
    if value.endswith(".exe"):
        value = value[:-4]
    return value


def _tokenize(text: str) -> set[str]:
    parts = re.split(r"[^a-z0-9]+", text.lower())
    return {p for p in parts if len(p) >= 2}


def _best_substring_hit(process: str, title: str, lexicon: set[str]) -> float:
    haystacks = [process, title]
    best = 0.0
    for term in lexicon:
        if len(term) < 3:
            continue
        for hay in haystacks:
            if not hay:
                continue
            if term == hay:
                return 1.0
            if term in hay or hay in term:
                best = max(best, min(1.0, len(term) / max(len(hay), 1)))
    return best

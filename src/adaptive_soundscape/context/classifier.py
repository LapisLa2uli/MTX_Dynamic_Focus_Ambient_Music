"""Rule-based work context classifier with lightweight unknown-window inference."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from adaptive_soundscape.context.inferer import ContextInferer, InferenceResult
from adaptive_soundscape.context.rules import (
    BROWSER_PROCESS_HINTS,
    CODE_FILE_EXTENSIONS,
    DEFAULT_RULES,
    WORK_BROWSER_KEYWORDS,
    ContextRule,
)
from adaptive_soundscape.context.user_mappings import UserMappings
from adaptive_soundscape.core.events import ActivitySnapshot, WorkContext


@dataclass(frozen=True)
class ClassificationResult:
    context: WorkContext
    confidence: float
    scores: dict[WorkContext, float]


@dataclass(frozen=True)
class ResolvedContext:
    """Final context after rules, user mappings, and optional inference."""

    context: WorkContext
    confidence: float
    source: str  # "rules" | "user" | "inferer" | "unknown"
    is_misc: bool
    needs_confirm: bool
    inference: InferenceResult | None = None
    process_name: str = ""
    window_title: str = ""


def _normalize(text: str) -> str:
    return text.lower().strip()


def _process_base(process_name: str) -> str:
    base = _normalize(process_name)
    if base.endswith(".exe"):
        base = base[:-4]
    return base


def _process_matches(process_name: str, names: tuple[str, ...]) -> bool:
    base = _process_base(process_name)
    if not base:
        return False
    for name in names:
        needle = name.lower().removesuffix(".exe")
        if base == needle or needle in base:
            return True
    return False


def _title_has_code_file(title: str) -> bool:
    lowered = _normalize(title)
    if any(ext in lowered for ext in CODE_FILE_EXTENSIONS):
        return True
    return bool(re.search(r"\b[\w.-]+\.(py|js|ts|tsx|jsx|java|go|rs|cpp|c|cs|rb|php)\b", lowered))


def _is_browser_process(process_name: str) -> bool:
    base = _process_base(process_name)
    return any(hint in base for hint in BROWSER_PROCESS_HINTS)


def _is_work_browser_tab(title: str) -> bool:
    lowered = _normalize(title)
    return any(keyword in lowered for keyword in WORK_BROWSER_KEYWORDS)


def _score_rule(rule: ContextRule, process_name: str, title: str) -> float:
    if rule.context == WorkContext.DISTRACTION:
        return _score_distraction(process_name, title, rule)

    score = 0.0
    if _process_matches(process_name, rule.process_names):
        score += 0.78 * rule.weight
    if title:
        for keyword in rule.title_keywords:
            if keyword.lower() in title:
                score += 0.35 * rule.weight
                break
    if rule.context == WorkContext.PROGRAMMING and _title_has_code_file(title):
        score += 0.45 * rule.weight
    return min(1.0, score)


def _score_distraction(process_name: str, title: str, rule: ContextRule) -> float:
    """Require explicit distraction signals; browsers are not distraction by default."""
    if not title and not _is_browser_process(process_name):
        return 0.0

    if _is_work_browser_tab(title):
        return 0.0

    score = 0.0
    for keyword in rule.title_keywords:
        if keyword.lower() in title:
            score += 0.55 * rule.weight
            break

    if score <= 0.0:
        return 0.0

    if _is_browser_process(process_name):
        score += 0.25 * rule.weight

    return min(1.0, score)


def classify_snapshot(
    snapshot: ActivitySnapshot,
    rules: tuple[ContextRule, ...] = DEFAULT_RULES,
) -> ClassificationResult:
    """Score each context from window/process metadata."""
    scores: dict[WorkContext, float] = {
        ctx: 0.0 for ctx in WorkContext if ctx != WorkContext.UNKNOWN
    }
    process = _normalize(snapshot.process_name)
    title = _normalize(snapshot.window_title)

    for rule in rules:
        score = _score_rule(rule, process, title)
        if score > 0:
            scores[rule.context] = max(scores[rule.context], score)

    if not any(scores.values()):
        return ClassificationResult(WorkContext.UNKNOWN, 0.0, scores)

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    confidence = scores[best]

    # Prefer a productive match when distraction only barely wins on a browser tab.
    if best == WorkContext.DISTRACTION and _is_browser_process(process):
        productive = max(
            (
                (ctx, value)
                for ctx, value in scores.items()
                if ctx != WorkContext.DISTRACTION and value > 0
            ),
            key=lambda item: item[1],
            default=(WorkContext.UNKNOWN, 0.0),
        )
        if productive[1] >= confidence - 0.12:
            best = productive[0]
            confidence = productive[1]

    return ClassificationResult(best, confidence, scores)


def resolve_context(
    snapshot: ActivitySnapshot,
    user_mappings: UserMappings | None = None,
    inferer: ContextInferer | None = None,
    *,
    min_rule_confidence: float = 0.25,
) -> ResolvedContext:
    """Classify with built-in rules + user mappings; infer when still misc/unknown."""
    mappings = user_mappings or UserMappings()
    process = snapshot.process_name
    title = snapshot.window_title

    # Explicit user process mappings always win so toast/editor choices stick
    # across restarts even when built-in rules score a different category higher.
    forced = _user_process_context(process, mappings)
    if forced is not None:
        return ResolvedContext(
            context=forced,
            confidence=1.0,
            source="user",
            is_misc=False,
            needs_confirm=False,
            process_name=process,
            window_title=title,
        )

    builtin = classify_snapshot(snapshot, rules=DEFAULT_RULES)
    user_rules = mappings.to_rules()
    merged_rules = DEFAULT_RULES + user_rules if user_rules else DEFAULT_RULES
    merged = classify_snapshot(snapshot, rules=merged_rules)

    if (
        merged.context != WorkContext.UNKNOWN
        and merged.confidence >= min_rule_confidence
    ):
        used_user = (
            builtin.context == WorkContext.UNKNOWN
            or builtin.confidence < min_rule_confidence
            or (
                user_rules
                and merged.context != builtin.context
                and merged.confidence >= builtin.confidence
            )
        )
        if _matches_user_mapping(process, title, mappings):
            used_user = True
        return ResolvedContext(
            context=merged.context,
            confidence=merged.confidence,
            source="user" if used_user else "rules",
            is_misc=False,
            needs_confirm=False,
            process_name=process,
            window_title=title,
        )

    engine = inferer or ContextInferer(mappings)
    inference = engine.infer(process, title)
    if inference.context != WorkContext.UNKNOWN:
        return ResolvedContext(
            context=inference.context,
            confidence=max(0.35, inference.confidence * 0.85),
            source="inferer",
            is_misc=True,
            needs_confirm=True,
            inference=inference,
            process_name=process,
            window_title=title,
        )

    return ResolvedContext(
        context=WorkContext.UNKNOWN,
        confidence=0.0,
        source="unknown",
        is_misc=True,
        needs_confirm=True,
        inference=inference,
        process_name=process,
        window_title=title,
    )


def resolve_window(
    process_name: str,
    window_title: str,
    *,
    user_mappings: UserMappings | None = None,
    inferer: ContextInferer | None = None,
) -> ResolvedContext:
    """Classify a single window without needing a live activity snapshot."""
    snapshot = ActivitySnapshot(
        timestamp=datetime.now(timezone.utc),
        window_title=window_title,
        process_name=process_name,
        keystroke_count=0,
        click_count=0,
        scroll_count=0,
        cpu_percent=0.0,
        idle_seconds=0.0,
    )
    return resolve_context(
        snapshot, user_mappings=user_mappings, inferer=inferer
    )


def collect_unclassified(
    windows: list[tuple[str, str]],
    *,
    user_mappings: UserMappings | None = None,
    inferer: ContextInferer | None = None,
) -> list[ResolvedContext]:
    """Return unique windows that still need a user classification."""
    mappings = user_mappings or UserMappings()
    seen: set[tuple[str, str]] = set()
    out: list[ResolvedContext] = []
    for process_name, window_title in windows:
        process = (process_name or "").strip()
        title = (window_title or "").strip()
        if not process and not title:
            continue
        key = (_process_base(process), title.lower())
        if key in seen:
            continue
        seen.add(key)
        resolved = resolve_window(
            process, title, user_mappings=mappings, inferer=inferer
        )
        if resolved.needs_confirm:
            out.append(resolved)
    return out


def _user_process_context(
    process_name: str, mappings: UserMappings
) -> WorkContext | None:
    """Return the category owning this process, if the user mapped it."""
    process = _process_base(process_name)
    if not process:
        return None
    for ctx, mapping in mappings.by_context.items():
        for name in mapping.process_names:
            needle = name.lower().removesuffix(".exe")
            if process == needle or needle in process:
                return ctx
    return None


def _matches_user_mapping(
    process_name: str, window_title: str, mappings: UserMappings
) -> bool:
    if _user_process_context(process_name, mappings) is not None:
        return True
    title = _normalize(window_title)
    for mapping in mappings.by_context.values():
        for keyword in mapping.title_keywords:
            if keyword and keyword in title:
                return True
    return False

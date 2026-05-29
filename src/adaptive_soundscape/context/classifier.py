"""Rule-based work context classifier."""

from __future__ import annotations

from dataclasses import dataclass

from adaptive_soundscape.context.rules import DEFAULT_RULES, ContextRule
from adaptive_soundscape.core.events import ActivitySnapshot, WorkContext


@dataclass(frozen=True)
class ClassificationResult:
    context: WorkContext
    confidence: float
    scores: dict[WorkContext, float]


def _normalize(text: str) -> str:
    return text.lower().strip()


def classify_snapshot(
    snapshot: ActivitySnapshot,
    rules: tuple[ContextRule, ...] = DEFAULT_RULES,
) -> ClassificationResult:
    """Score each context from window/process metadata."""
    scores: dict[WorkContext, float] = {ctx: 0.0 for ctx in WorkContext if ctx != WorkContext.UNKNOWN}
    process = _normalize(snapshot.process_name)
    title = _normalize(snapshot.window_title)

    for rule in rules:
        score = 0.0
        for name in rule.process_names:
            if name.lower() in process:
                score += 0.6 * rule.weight
        for keyword in rule.title_keywords:
            if keyword.lower() in title:
                score += 0.4 * rule.weight
        if score > 0:
            scores[rule.context] = max(scores[rule.context], min(1.0, score))

    if not any(scores.values()):
        return ClassificationResult(WorkContext.UNKNOWN, 0.0, scores)

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    confidence = scores[best]
    return ClassificationResult(best, confidence, scores)

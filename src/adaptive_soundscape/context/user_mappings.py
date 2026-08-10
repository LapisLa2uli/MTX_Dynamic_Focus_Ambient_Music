"""Persistent user-configured context name mappings."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from adaptive_soundscape.context.rules import ContextRule
from adaptive_soundscape.core.events import WorkContext

logger = logging.getLogger(__name__)

CONFIGURABLE_CONTEXTS: tuple[WorkContext, ...] = tuple(
    ctx for ctx in WorkContext if ctx != WorkContext.UNKNOWN
)


def default_mappings_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / "user_context_mappings.json"


@dataclass
class CategoryMapping:
    process_names: list[str] = field(default_factory=list)
    title_keywords: list[str] = field(default_factory=list)

    def normalized(self) -> CategoryMapping:
        return CategoryMapping(
            process_names=_unique_normalized(self.process_names),
            title_keywords=_unique_normalized(self.title_keywords),
        )


@dataclass
class UserMappings:
    """Per-category process names and title keywords configured by the user."""

    by_context: dict[WorkContext, CategoryMapping] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for ctx in CONFIGURABLE_CONTEXTS:
            self.by_context.setdefault(ctx, CategoryMapping())

    def get(self, context: WorkContext) -> CategoryMapping:
        return self.by_context.setdefault(context, CategoryMapping())

    def set_category(
        self,
        context: WorkContext,
        *,
        process_names: list[str] | None = None,
        title_keywords: list[str] | None = None,
    ) -> None:
        mapping = self.get(context)
        if process_names is not None:
            mapping.process_names = _unique_normalized(process_names)
        if title_keywords is not None:
            mapping.title_keywords = _unique_normalized(title_keywords)

    def add_process(self, context: WorkContext, process_name: str) -> None:
        name = _normalize_token(process_name)
        if not name or context == WorkContext.UNKNOWN:
            return
        # Remove from other categories so a process has one owner.
        for ctx, mapping in self.by_context.items():
            mapping.process_names = [
                p for p in mapping.process_names if p != name
            ]
        mapping = self.get(context)
        if name not in mapping.process_names:
            mapping.process_names.append(name)

    def add_title_keyword(self, context: WorkContext, keyword: str) -> None:
        key = _normalize_token(keyword)
        if not key or context == WorkContext.UNKNOWN:
            return
        mapping = self.get(context)
        if key not in mapping.title_keywords:
            mapping.title_keywords.append(key)

    def to_rules(self, weight: float = 1.45) -> tuple[ContextRule, ...]:
        rules: list[ContextRule] = []
        for ctx in CONFIGURABLE_CONTEXTS:
            mapping = self.get(ctx).normalized()
            if not mapping.process_names and not mapping.title_keywords:
                continue
            rules.append(
                ContextRule(
                    context=ctx,
                    process_names=tuple(mapping.process_names),
                    title_keywords=tuple(mapping.title_keywords),
                    weight=weight,
                )
            )
        return tuple(rules)

    def to_dict(self) -> dict[str, dict[str, list[str]]]:
        out: dict[str, dict[str, list[str]]] = {}
        for ctx in CONFIGURABLE_CONTEXTS:
            mapping = self.get(ctx).normalized()
            out[ctx.value] = {
                "process_names": list(mapping.process_names),
                "title_keywords": list(mapping.title_keywords),
            }
        return out

    @classmethod
    def from_dict(cls, data: dict) -> UserMappings:
        mappings = cls()
        if not isinstance(data, dict):
            return mappings
        for key, value in data.items():
            try:
                ctx = WorkContext(str(key))
            except ValueError:
                continue
            if ctx == WorkContext.UNKNOWN or not isinstance(value, dict):
                continue
            processes = value.get("process_names", [])
            titles = value.get("title_keywords", [])
            mappings.set_category(
                ctx,
                process_names=[str(x) for x in processes] if isinstance(processes, list) else [],
                title_keywords=[str(x) for x in titles] if isinstance(titles, list) else [],
            )
        return mappings


def load_user_mappings(path: Path | None = None) -> UserMappings:
    target = path or default_mappings_path()
    if not target.exists():
        return UserMappings()
    try:
        with target.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return UserMappings.from_dict(data)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load user context mappings from %s: %s", target, exc)
        return UserMappings()


def save_user_mappings(mappings: UserMappings, path: Path | None = None) -> Path:
    target = path or default_mappings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(mappings.to_dict(), handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return target


def _normalize_token(value: str) -> str:
    text = value.lower().strip()
    if text.endswith(".exe"):
        text = text[:-4]
    return text


def _unique_normalized(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        token = _normalize_token(value)
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out

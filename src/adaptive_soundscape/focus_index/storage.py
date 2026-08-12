"""SQLite persistence for FLI events, aggregates, and calibration patterns."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from adaptive_soundscape.focus_index.config import FocusIndexConfig, default_db_path
from adaptive_soundscape.focus_index.models import (
    AppActivityEvent,
    AttentionProbeEvent,
    ContextSwitchEvent,
    FocusEvent,
    FocusIndexResult,
    IdleStateEvent,
    SessionConfigEvent,
)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class FocusIndexStorage:
    """Local-only SQLite store. Never writes titles/URLs/key contents."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                task_profile TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_profile ON events(task_profile);

            CREATE TABLE IF NOT EXISTS aggregates (
                id TEXT PRIMARY KEY,
                task_profile TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                focus_index REAL,
                measured_focus REAL,
                pattern_focus REAL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agg_profile ON aggregates(task_profile);

            CREATE TABLE IF NOT EXISTS patterns (
                id TEXT PRIMARY KEY,
                task_profile TEXT NOT NULL,
                created_at TEXT NOT NULL,
                scope TEXT NOT NULL,
                features TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_patterns_profile ON patterns(task_profile);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def insert_event(self, event: FocusEvent) -> None:
        payload = event.model_dump(mode="json")
        self._conn.execute(
            "INSERT OR REPLACE INTO events(event_id, event_type, timestamp, task_profile, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                payload.get("event_id", str(uuid4())),
                payload["event_type"],
                _iso(event.timestamp),
                getattr(event, "task_profile", "default"),
                json.dumps(payload),
            ),
        )
        self._conn.commit()

    def insert_events(self, events: Iterable[FocusEvent]) -> None:
        for event in events:
            self.insert_event(event)

    def load_events(
        self,
        *,
        start: datetime,
        end: datetime,
        task_profile: str | None = None,
    ) -> list[FocusEvent]:
        sql = "SELECT payload FROM events WHERE timestamp >= ? AND timestamp <= ?"
        params: list[Any] = [_iso(start), _iso(end)]
        if task_profile is not None:
            sql += " AND task_profile = ?"
            params.append(task_profile)
        sql += " ORDER BY timestamp ASC"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._deserialize(json.loads(row["payload"])) for row in rows]

    def _deserialize(self, payload: dict[str, Any]) -> FocusEvent:
        et = payload.get("event_type")
        mapping = {
            "app_activity": AppActivityEvent,
            "context_switch": ContextSwitchEvent,
            "idle_state": IdleStateEvent,
            "attention_probe": AttentionProbeEvent,
            "session_config": SessionConfigEvent,
        }
        model = mapping.get(et)
        if model is None:
            raise ValueError(f"Unknown event_type: {et}")
        return model.model_validate(payload)

    def save_aggregate(self, result: FocusIndexResult) -> None:
        payload = result.model_dump(mode="json")
        self._conn.execute(
            "INSERT OR REPLACE INTO aggregates("
            "id, task_profile, window_start, window_end, focus_index, "
            "measured_focus, pattern_focus, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                result.task_profile,
                _iso(result.window_start) if result.window_start else "",
                _iso(result.window_end) if result.window_end else "",
                result.focus_index,
                result.measured_focus,
                result.pattern_focus,
                json.dumps(payload),
            ),
        )
        self._conn.commit()

    def load_focus_values(self, task_profile: str) -> list[float]:
        rows = self._conn.execute(
            "SELECT focus_index FROM aggregates WHERE task_profile = ? "
            "AND focus_index IS NOT NULL ORDER BY window_end ASC",
            (task_profile,),
        ).fetchall()
        return [float(r["focus_index"]) for r in rows]

    def save_pattern(
        self,
        *,
        task_profile: str,
        features: dict[str, float],
        scope: str = "dedicated",
        pattern_id: str | None = None,
    ) -> str:
        pid = pattern_id or str(uuid4())
        self._conn.execute(
            "INSERT OR REPLACE INTO patterns(id, task_profile, created_at, scope, features) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                pid,
                task_profile,
                _iso(datetime.now(timezone.utc)),
                scope,
                json.dumps(features),
            ),
        )
        self._conn.commit()
        return pid

    def load_patterns(
        self, task_profile: str, *, include_session: bool = True
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, task_profile, created_at, scope, features FROM patterns "
            "WHERE task_profile = ? ORDER BY created_at DESC",
            (task_profile,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            if not include_session and row["scope"] == "session":
                continue
            out.append(
                {
                    "id": row["id"],
                    "task_profile": row["task_profile"],
                    "created_at": row["created_at"],
                    "scope": row["scope"],
                    "features": json.loads(row["features"]),
                }
            )
        return out

    def delete_session_patterns(self, task_profile: str | None = None) -> None:
        if task_profile is None:
            self._conn.execute("DELETE FROM patterns WHERE scope = 'session'")
        else:
            self._conn.execute(
                "DELETE FROM patterns WHERE scope = 'session' AND task_profile = ?",
                (task_profile,),
            )
        self._conn.commit()

    def purge(self, retention_days: int | None = None, config: FocusIndexConfig | None = None) -> int:
        days = retention_days
        if days is None:
            days = config.retention_days if config is not None else 7
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(days))
        cur = self._conn.execute(
            "DELETE FROM events WHERE timestamp < ?", (_iso(cutoff),)
        )
        self._conn.execute(
            "DELETE FROM aggregates WHERE window_end != '' AND window_end < ?",
            (_iso(cutoff),),
        )
        self._conn.commit()
        return int(cur.rowcount)

    def export_json(self) -> dict[str, Any]:
        events = [
            json.loads(r["payload"])
            for r in self._conn.execute("SELECT payload FROM events ORDER BY timestamp").fetchall()
        ]
        aggregates = [
            json.loads(r["payload"])
            for r in self._conn.execute(
                "SELECT payload FROM aggregates ORDER BY window_end"
            ).fetchall()
        ]
        patterns = self._conn.execute(
            "SELECT id, task_profile, created_at, scope, features FROM patterns"
        ).fetchall()
        return {
            "events": events,
            "aggregates": aggregates,
            "patterns": [
                {
                    "id": r["id"],
                    "task_profile": r["task_profile"],
                    "created_at": r["created_at"],
                    "scope": r["scope"],
                    "features": json.loads(r["features"]),
                }
                for r in patterns
            ],
        }

    def delete_all(self) -> None:
        self._conn.execute("DELETE FROM events")
        self._conn.execute("DELETE FROM aggregates")
        self._conn.execute("DELETE FROM patterns")
        self._conn.commit()

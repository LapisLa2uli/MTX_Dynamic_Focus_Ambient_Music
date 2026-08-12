"""Demo: score synthetic FLI windows and print results."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from adaptive_soundscape.focus_index.config import FocusIndexConfig
from adaptive_soundscape.focus_index.patterns import max_similarity, vector_from_events
from adaptive_soundscape.focus_index.scoring import score_window
from adaptive_soundscape.focus_index.service import FocusIndexService
from adaptive_soundscape.focus_index.synthetic import (
    aligned_session,
    distracting_session,
    idle_heavy_session,
)


def _run_case(name: str, events, profile: str = "programming") -> None:
    start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=10)
    config = FocusIndexConfig()
    vec = vector_from_events(events, window_start=start, window_end=end, config=config)
    result = score_window(
        events, window_start=start, window_end=end, config=config, pattern_similarity=None
    )
    result.task_profile = profile
    print(f"\n=== {name} ===")
    print(
        json.dumps(
            {
                "focus_index": result.focus_index,
                "measured_focus": result.measured_focus,
                "pattern_focus": result.pattern_focus,
                "focus_source": result.focus_source,
                "band": result.focus_band,
                "status": result.status,
                "components": result.components.model_dump(),
                "uncertainties": result.uncertainties,
            },
            indent=2,
            default=str,
        )
    )
    return vec


def main() -> None:
    aligned = aligned_session()
    distract = distracting_session()
    idle = idle_heavy_session()

    calib_vec = _run_case("aligned session (no pattern)", aligned)
    _run_case("distracting session", distract)
    _run_case("idle-heavy session", idle)

    tmp = tempfile.mkdtemp()
    try:
        db = Path(tmp) / "demo.sqlite"
        svc = FocusIndexService(config=FocusIndexConfig(db_path=db), db_path=db)
        for event in aligned:
            svc.storage.insert_event(event)
        svc.storage.save_pattern(
            task_profile="programming", features=calib_vec, scope="dedicated"
        )
        start = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(minutes=10)
        mid_vec = vector_from_events(
            distract, window_start=start, window_end=end, config=svc.config
        )
        sim = max_similarity(mid_vec, svc.storage.load_patterns("programming"))
        result = score_window(
            distract,
            window_start=start,
            window_end=end,
            config=svc.config,
            pattern_similarity=sim,
        )
        print("\n=== distracting + calibrated pattern max() ===")
        print(
            json.dumps(
                {
                    "measured_focus": result.measured_focus,
                    "pattern_similarity": result.pattern_similarity,
                    "pattern_focus": result.pattern_focus,
                    "focus_index": result.focus_index,
                    "focus_source": result.focus_source,
                },
                indent=2,
                default=str,
            )
        )
        svc.storage.close()
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()

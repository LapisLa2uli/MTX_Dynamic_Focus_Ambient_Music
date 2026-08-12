"""FocusIndexService — window orchestration API for the live app."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from adaptive_soundscape.cognitive.estimator import FocusEstimate
from adaptive_soundscape.core.events import ActivitySnapshot, FocusState, WorkContext
from adaptive_soundscape.focus_index.baseline import baseline_for_profile
from adaptive_soundscape.focus_index.collectors import ActivityBridge
from adaptive_soundscape.focus_index.config import FocusIndexConfig
from adaptive_soundscape.focus_index.models import (
    AttentionProbeEvent,
    FocusIndexResult,
    FocusStatus,
    SessionConfigEvent,
)
from adaptive_soundscape.focus_index.patterns import max_similarity, vector_from_events
from adaptive_soundscape.focus_index.scoring import score_window
from adaptive_soundscape.focus_index.storage import FocusIndexStorage


def _band_to_focus_state(result: FocusIndexResult, context: WorkContext) -> FocusState:
    if result.focus_band.value == "uncertain" or result.status == FocusStatus.INSUFFICIENT:
        return FocusState.CALM_PRODUCTIVITY
    score = result.as_unit_score()
    if context == WorkContext.DISTRACTION and score < 0.45:
        return FocusState.MILD_DISTRACTION
    if score >= 0.82:
        return FocusState.DEEP_FOCUS
    if score >= 0.65:
        return FocusState.DEEP_FOCUS
    if score >= 0.45:
        return FocusState.CALM_PRODUCTIVITY
    return FocusState.MILD_DISTRACTION


class FocusIndexService:
    """Collect privacy-safe events and score the rolling window."""

    def __init__(
        self,
        config: FocusIndexConfig | None = None,
        storage: FocusIndexStorage | None = None,
        db_path: Path | None = None,
    ) -> None:
        self.config = config or FocusIndexConfig()
        if db_path is not None:
            self.config.db_path = db_path
        self.storage = storage or FocusIndexStorage(self.config.db_path)
        self.bridge = ActivityBridge(
            task_profile="default",
            idle_threshold_s=self.config.idle_threshold_s,
        )
        self._force_aligned = False
        self._last_result: FocusIndexResult | None = None
        self._ema = 0.5
        self.smoothing = 0.40
        # Snappier bar motion before the user has calibration patterns.
        self.uncalibrated_smoothing = 0.18
        # Asymmetric fall/rise: drop focus faster than it recovers.
        self.fall_smoothing_calibrated = 0.22
        self.fall_smoothing_uncalibrated = 0.10
        self.sensitivity = 1.0

    def set_sensitivity(self, value: float) -> None:
        """Map Settings sensitivity (0.2–2.0) onto FLI aggressiveness."""
        self.sensitivity = max(0.2, min(2.0, float(value)))

    def set_task_profile(self, task_profile: str) -> None:
        self.bridge.set_task_profile(task_profile)
        self.storage.insert_event(
            SessionConfigEvent(task_profile=task_profile, probes_enabled=True)
        )

    def set_calibration_mode(self, enabled: bool, *, force_aligned: bool = True) -> None:
        self.bridge.set_calibration(enabled)
        self._force_aligned = bool(enabled and force_aligned)

    def ingest_tick(
        self,
        snapshot: ActivitySnapshot,
        context: WorkContext,
        *,
        interval_s: float,
    ) -> None:
        events = self.bridge.ingest(
            snapshot,
            context,
            interval_s=interval_s,
            force_aligned=self._force_aligned,
        )
        for event in events:
            self.storage.insert_event(event)

    def record_probe(self, event: AttentionProbeEvent) -> None:
        self.storage.insert_event(event)

    def has_calibration_patterns(self, task_profile: str | None = None) -> bool:
        """True when a dedicated or session pattern exists for the profile."""
        profile = task_profile or self.bridge.task_profile
        patterns = self.storage.load_patterns(profile, include_session=True)
        return bool(patterns)

    def score_current_window(
        self,
        *,
        task_profile: str | None = None,
        now: datetime | None = None,
        persist: bool = True,
    ) -> FocusIndexResult:
        end = now or datetime.now(timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        start = end - timedelta(seconds=self.config.window_seconds)
        profile = task_profile or self.bridge.task_profile
        events = self.storage.load_events(start=start, end=end)
        # Prefer events for profile but include unscoped recent ticks.
        profile_events = [
            e for e in events if getattr(e, "task_profile", profile) == profile
        ]
        use_events = profile_events or events

        patterns = self.storage.load_patterns(profile, include_session=True)
        calibrated = bool(patterns)

        if calibrated:
            current_vec = vector_from_events(
                use_events,
                window_start=start,
                window_end=end,
                config=self.config,
            )
            similarity = max_similarity(current_vec, patterns)
            measured_keys: tuple[str, ...] = ("A", "S", "I", "P")
        else:
            # Default non-preference metric: weighted A/S/I only (no probe / pattern).
            similarity = None
            measured_keys = ("A", "S", "I")

        baseline = baseline_for_profile(self.storage, profile, self.config)
        result = score_window(
            use_events,
            window_start=start,
            window_end=end,
            config=self.config,
            pattern_similarity=similarity,
            baseline_status=baseline.status
            if baseline.status == FocusStatus.CALIBRATING
            else None,
            measured_keys=measured_keys,
        )
        result.task_profile = profile
        result.extras["baseline_samples"] = baseline.sample_count
        result.extras["baseline_median"] = baseline.median
        result.extras["calibrated"] = calibrated
        if persist and result.focus_index is not None:
            self.storage.save_aggregate(result)
        self._last_result = result
        return result

    def estimate_for_app(
        self,
        snapshot: ActivitySnapshot,
        context: WorkContext,
        *,
        interval_s: float,
    ) -> FocusEstimate:
        """Adapter: ingest + score → FocusEstimate for MusicDirector path."""
        self.ingest_tick(snapshot, context, interval_s=interval_s)
        # Temporarily scale switch/recency by sensitivity for this score pass.
        cfg = self.config
        base_switch = cfg.switch_rate_ref
        base_tau = cfg.recency_tau_seconds
        sens = max(0.2, float(self.sensitivity))
        cfg.switch_rate_ref = max(0.4, base_switch / sens)
        cfg.recency_tau_seconds = max(20.0, base_tau / sens)
        try:
            result = self.score_current_window(persist=True)
        finally:
            cfg.switch_rate_ref = base_switch
            cfg.recency_tau_seconds = base_tau

        raw = result.as_unit_score()
        calibrated = bool(result.extras.get("calibrated"))
        if raw < self._ema:
            alpha = (
                self.fall_smoothing_calibrated
                if calibrated
                else self.fall_smoothing_uncalibrated
            )
        else:
            alpha = self.smoothing if calibrated else self.uncalibrated_smoothing
        alpha = max(0.0, min(0.99, float(alpha)))
        self._ema = alpha * self._ema + (1.0 - alpha) * raw
        score = max(0.0, min(1.0, self._ema))
        state = _band_to_focus_state(result, context)
        return FocusEstimate(focus_score=score, state=state, raw_score=raw)

    @property
    def last_result(self) -> FocusIndexResult | None:
        return self._last_result

    def save_calibration_pattern(
        self,
        *,
        task_profile: str,
        scope: str = "dedicated",
        now: datetime | None = None,
        window_seconds: float | None = None,
    ) -> str:
        end = now or datetime.now(timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        seconds = window_seconds or self.config.window_seconds
        start = end - timedelta(seconds=seconds)
        events = self.storage.load_events(start=start, end=end, task_profile=task_profile)
        if not events:
            events = self.storage.load_events(start=start, end=end)
        features = vector_from_events(
            events, window_start=start, window_end=end, config=self.config
        )
        return self.storage.save_pattern(
            task_profile=task_profile, features=features, scope=scope
        )

    def purge(self) -> int:
        return self.storage.purge(config=self.config)

    def export_data(self) -> dict:
        return self.storage.export_json()

    def delete_all_data(self) -> None:
        self.storage.delete_all()

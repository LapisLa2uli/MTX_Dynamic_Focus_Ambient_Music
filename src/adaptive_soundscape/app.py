"""Application orchestrator wiring all subsystems."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QTimer

from adaptive_soundscape.activity.monitor import ActivityMonitor
from adaptive_soundscape.audio.factory import create_audio_backend
from adaptive_soundscape.cognitive.estimator import FocusEstimator
from adaptive_soundscape.cognitive.signals import FocusSignals
from adaptive_soundscape.context.classifier import classify_snapshot
from adaptive_soundscape.context.persistence import ContextPersistence
from adaptive_soundscape.core.bus import EventBus
from adaptive_soundscape.core.config import Settings, load_settings, resolve_assets_dir
from adaptive_soundscape.core.events import (
    ActivitySnapshot,
    AudioParametersUpdated,
    ContextChanged,
    FocusUpdated,
    FocusState,
    ManualOverrideChanged,
    PrivacySettingsChanged,
    WorkContext,
)
from adaptive_soundscape.transition.controller import TransitionController
from adaptive_soundscape.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


class AdaptiveSoundscapeApp:
    """Coordinates monitoring, classification, estimation, audio, and UI."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.bus = EventBus()
        self.monitor = ActivityMonitor(self.settings.privacy)
        self.persistence = ContextPersistence(
            dwell_seconds=float(self.settings.context.default_dwell_seconds)
        )
        self.estimator = FocusEstimator(
            sensitivity=self.settings.cognitive.sensitivity,
            smoothing=self.settings.cognitive.focus_smoothing,
        )
        self.transition = TransitionController(
            deep_focus_crossfade_seconds=self.settings.transition.deep_focus_crossfade_seconds,
            distraction_recovery_seconds=self.settings.transition.distraction_recovery_seconds,
            cooldown_seconds=self.settings.transition.cooldown_seconds,
            hysteresis_threshold=self.settings.transition.hysteresis_threshold,
        )
        assets = resolve_assets_dir(self.settings)
        self._ensure_audio_assets(assets)
        self.audio = create_audio_backend(self.settings, assets)
        self.window = MainWindow()
        self._manual_override = False
        self._current_context = WorkContext.UNKNOWN
        self._current_focus = FocusState.CALM_PRODUCTIVITY
        self._focus_score = 0.5
        self._audio_running = False

        interval = self.settings.app.poll_interval_ms
        self._timer = QTimer()
        self._timer.setInterval(interval)
        self._timer.timeout.connect(self._tick)

        self.window._audio_btn.clicked.connect(self._toggle_audio)
        self.window._override_check.toggled.connect(self._on_override)
        self.window._sensitivity_spin.valueChanged.connect(self._on_sensitivity)
        for chk in (self.window._title_check, self.window._process_check, self.window._log_check):
            chk.toggled.connect(self._on_privacy)

        self.bus.subscribe(ActivitySnapshot, self._on_activity)
        self.bus.subscribe(ContextChanged, self._on_context)
        self.bus.subscribe(FocusUpdated, self._on_focus)

    def _ensure_audio_assets(self, assets_dir: Path) -> None:
        from adaptive_soundscape.audio.asset_generator import ensure_assets

        ensure_assets(assets_dir)

    def start(self) -> None:
        if self.settings.app.logging_enabled:
            logging.basicConfig(level=logging.INFO)
        self.monitor.start()
        self._timer.start()
        self.window.show()
        self._refresh_ui()

    def stop(self) -> None:
        self._timer.stop()
        self.monitor.stop()
        self.audio.stop()

    def _toggle_audio(self) -> None:
        if self._audio_running:
            self.audio.stop()
            self._audio_running = False
            self.window._audio_btn.setText("Start Audio")
            self.window.set_status_message("")
        else:
            decision = self.transition.decide(
                self._current_context, self._current_focus, self._focus_score
            )
            try:
                self.audio.start(profile_id=decision.profile_id)
            except Exception as exc:
                logger.exception("Failed to start audio backend")
                if self.settings.audio.fallback_to_placeholder:
                    try:
                        assets = resolve_assets_dir(self.settings)
                        self.audio.stop()
                        self.audio = create_audio_backend(
                            self._placeholder_settings(), assets
                        )
                        self.audio.start(profile_id=decision.profile_id)
                        self.window.set_status_message(
                            "Using built-in audio mixer (Godot unavailable)."
                        )
                    except Exception as fallback_exc:
                        logger.exception("Placeholder audio fallback failed")
                        self.window.set_status_message(f"Audio error: {fallback_exc}")
                        return
                else:
                    self.window.set_status_message(f"Audio error: {exc}")
                    return
            self._audio_running = True
            self.window._audio_btn.setText("Stop Audio")
            self._apply_audio(decision)

    def _placeholder_settings(self) -> Settings:
        """Return settings forced to the placeholder mixer backend."""
        return self.settings.model_copy(
            update={
                "audio": self.settings.audio.model_copy(update={"backend": "placeholder"})
            }
        )

    def _on_override(self, enabled: bool) -> None:
        self._manual_override = enabled
        event = ManualOverrideChanged(enabled=enabled, context=self.window.manual_context)
        self.bus.publish(event)
        if enabled:
            ctx = self.window.manual_context
            self.persistence.force(ctx)
            decision = self.transition.force_profile(ctx, self._current_focus)
            self._apply_audio(decision)

    def _on_sensitivity(self, value: float) -> None:
        self.estimator.sensitivity = value

    def _on_privacy(self, _checked: bool) -> None:
        titles, processes, log_activity = self.window.privacy_settings()
        self.monitor._privacy.collect_window_titles = titles
        self.monitor._privacy.collect_process_names = processes
        self.settings.privacy.log_activity = log_activity
        self.bus.publish(
            PrivacySettingsChanged(
                collect_window_titles=titles,
                collect_process_names=processes,
                log_activity=log_activity,
            )
        )

    def _tick(self) -> None:
        interval = self.settings.app.poll_interval_ms / 1000.0
        snapshot = self.monitor.poll(interval)
        self.bus.publish(snapshot)

        result = classify_snapshot(snapshot)
        if self._manual_override:
            ctx = self.window.manual_context
            confidence = 1.0
        else:
            ctx = self.persistence.update(result.context, result.confidence)
            confidence = result.confidence

        if ctx != self._current_context:
            self.bus.publish(ContextChanged(self._current_context, ctx, confidence))
            self._current_context = ctx

        metrics = self.monitor.metrics(snapshot, interval)
        signals = FocusSignals(
            input_rate=metrics.input_rate,
            switch_rate=metrics.switch_rate,
            idle_ratio=metrics.idle_ratio,
            cpu_load=metrics.cpu_load,
            context=ctx,
            context_confidence=confidence,
        )
        estimate = self.estimator.estimate(signals)
        if estimate.state != self._current_focus or abs(estimate.focus_score - self._focus_score) > 0.01:
            self.bus.publish(FocusUpdated(estimate.focus_score, estimate.state))
        self._current_focus = estimate.state
        self._focus_score = estimate.focus_score

        decision = self.transition.decide(ctx, estimate.state, estimate.focus_score)
        if decision.should_transition and self._audio_running:
            self._apply_audio(decision)

        self._refresh_ui(decision.display_name)
        self.monitor.reset_window_switches()

        if self.settings.privacy.log_activity and self.settings.app.logging_enabled:
            logger.info(
                "activity context=%s focus=%.2f state=%s",
                ctx.value,
                estimate.focus_score,
                estimate.state.value,
            )

    def _apply_audio(self, decision) -> None:
        self.audio.crossfade_to(
            decision.profile_id,
            decision.crossfade_seconds,
            decision.parameters,
        )
        self.bus.publish(
            AudioParametersUpdated(
                profile_id=decision.profile_id,
                brightness=decision.parameters.brightness,
                energy=decision.parameters.energy,
                warmth=decision.parameters.warmth,
                crossfade_seconds=decision.crossfade_seconds,
            )
        )

    def _on_activity(self, event: ActivitySnapshot) -> None:
        del event

    def _on_context(self, event: ContextChanged) -> None:
        del event

    def _on_focus(self, event: FocusUpdated) -> None:
        del event

    def _refresh_ui(self, profile_name: str = "Neutral") -> None:
        self.window.update_status(
            context=self._current_context,
            focus_state=self._current_focus,
            focus_score=self._focus_score,
            profile_name=profile_name,
        )

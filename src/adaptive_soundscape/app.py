"""Application orchestrator wiring all subsystems."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QTimer

from adaptive_soundscape.activity.monitor import ActivityMonitor
from adaptive_soundscape.audio.factory import create_audio_backend
from adaptive_soundscape.cognitive.estimator import FocusEstimator
from adaptive_soundscape.cognitive.signals import FocusSignals
from adaptive_soundscape.context.classifier import resolve_context
from adaptive_soundscape.context.inferer import ContextInferer
from adaptive_soundscape.context.persistence import ContextPersistence
from adaptive_soundscape.context.user_mappings import (
    load_user_mappings,
    save_user_mappings,
)
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
from adaptive_soundscape.ui.album_manager import AlbumManagerDialog
from adaptive_soundscape.ui.category_editor import CategoryEditorDialog
from adaptive_soundscape.ui.inference_toast import InferenceToast
from adaptive_soundscape.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


class AdaptiveSoundscapeApp:
    """Coordinates monitoring, classification, estimation, audio, and UI."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.bus = EventBus()
        self.monitor = ActivityMonitor(self.settings.privacy)
        self.persistence = ContextPersistence(
            dwell_seconds=float(self.settings.context.default_dwell_seconds),
            dwell_seconds_min=float(self.settings.context.dwell_seconds_min),
            dwell_seconds_max=float(self.settings.context.dwell_seconds_max),
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

        self.user_mappings = load_user_mappings()
        self.inferer = ContextInferer(self.user_mappings)
        self._toast = InferenceToast()
        self._prompted_processes: set[str] = set()
        self._dismissed_processes: set[str] = set()
        self._last_process_key = ""

        interval = self.settings.app.poll_interval_ms
        self._timer = QTimer()
        self._timer.setInterval(interval)
        self._timer.timeout.connect(self._tick)

        self.window._audio_btn.clicked.connect(self._toggle_audio)
        self.window._categories_btn.clicked.connect(self._open_category_editor)
        self.window._albums_btn.clicked.connect(self._open_album_manager)
        self.window._override_check.toggled.connect(self._on_override)
        self.window._sensitivity_spin.valueChanged.connect(self._on_sensitivity)
        for chk in (self.window._title_check, self.window._process_check, self.window._log_check):
            chk.toggled.connect(self._on_privacy)

        self._toast.confirmed.connect(self._on_inference_confirmed)
        self._toast.dismissed.connect(self._on_inference_dismissed)

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
        self._toast.hide()

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

    def _open_category_editor(self) -> None:
        updated = CategoryEditorDialog.edit(self.user_mappings, self.window)
        if updated is None:
            return
        self.user_mappings = updated
        self.inferer.set_user_mappings(updated)
        save_user_mappings(updated)
        self._prompted_processes.clear()
        self._dismissed_processes.clear()
        self.window.set_status_message("Category mappings saved.")

    def _open_album_manager(self) -> None:
        assets = resolve_assets_dir(self.settings)
        changed = AlbumManagerDialog.run(assets, self.window)
        if not changed:
            return
        invalidate = getattr(self.audio, "invalidate_caches", None)
        if callable(invalidate):
            invalidate()
        self.window.set_status_message(
            "Album updated. New tracks apply on the next scenario transition."
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
            self._toast.hide()

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

        resolved = resolve_context(
            snapshot,
            user_mappings=self.user_mappings,
            inferer=self.inferer,
        )
        if self._manual_override:
            ctx = self.window.manual_context
            confidence = 1.0
        else:
            ctx = self.persistence.update(resolved.context, resolved.confidence)
            confidence = resolved.confidence
            self._maybe_prompt_misc(resolved)

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
                "activity context=%s focus=%.2f state=%s source=%s",
                ctx.value,
                estimate.focus_score,
                estimate.state.value,
                resolved.source,
            )

    def _maybe_prompt_misc(self, resolved) -> None:
        process_key = _process_key(resolved.process_name)
        if process_key != self._last_process_key:
            self._last_process_key = process_key
            # Allow a new prompt when the foreground app changes.
            if process_key in self._prompted_processes and process_key not in self._dismissed_processes:
                pass

        if not resolved.needs_confirm or not resolved.is_misc:
            if self._toast.is_showing_for(resolved.process_name):
                # Window became known (e.g. user mapping applied elsewhere).
                self._toast.hide()
            return

        if not process_key:
            return
        if process_key in self._dismissed_processes:
            return
        if process_key in self._prompted_processes and self._toast.isVisible():
            return
        if process_key in self._prompted_processes and not self._toast.isVisible():
            # Already handled this process this session.
            return

        suggested = resolved.context
        confidence = resolved.confidence
        source = resolved.source
        if resolved.inference is not None and resolved.inference.context != WorkContext.UNKNOWN:
            suggested = resolved.inference.context
            confidence = resolved.inference.confidence
            source = resolved.inference.source

        self._prompted_processes.add(process_key)
        self._toast.show_inference(
            process_name=resolved.process_name,
            window_title=resolved.window_title,
            suggested=suggested,
            confidence=confidence,
            source=source,
        )

    def _on_inference_confirmed(
        self, process_name: str, window_title: str, context: object
    ) -> None:
        if not isinstance(context, WorkContext) or context == WorkContext.UNKNOWN:
            return
        self.user_mappings.add_process(context, process_name)
        # Optional distinctive title token helps browsers / multi-purpose apps.
        token = _distinctive_title_token(window_title)
        if token:
            self.user_mappings.add_title_keyword(context, token)
        save_user_mappings(self.user_mappings)
        self.inferer.set_user_mappings(self.user_mappings)

        key = _process_key(process_name)
        self._dismissed_processes.discard(key)
        self._prompted_processes.add(key)

        self.persistence.force(context)
        self._current_context = context
        decision = self.transition.force_profile(context, self._current_focus)
        if self._audio_running:
            self._apply_audio(decision)
        self.window.set_status_message(
            f"Saved '{process_name or key}' → {context.value.replace('_', ' ')}."
        )
        self._refresh_ui(decision.display_name)

    def _on_inference_dismissed(self, process_key: str) -> None:
        if process_key:
            self._dismissed_processes.add(process_key)

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


def _process_key(process_name: str) -> str:
    key = process_name.lower().strip()
    if key.endswith(".exe"):
        key = key[:-4]
    return key


def _distinctive_title_token(title: str) -> str | None:
    """Pick a short non-generic title token worth remembering."""
    import re

    stop = {
        "untitled",
        "document",
        "window",
        "chrome",
        "edge",
        "firefox",
        "new",
        "tab",
        "https",
        "http",
        "www",
        "com",
        "org",
    }
    parts = [p for p in re.split(r"[^a-zA-Z0-9]+", title.lower()) if len(p) >= 4]
    for part in parts:
        if part not in stop:
            return part
    return None

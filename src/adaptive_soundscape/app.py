"""Application orchestrator wiring all subsystems."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from adaptive_soundscape.activity.monitor import ActivityMonitor
from adaptive_soundscape.audio.factory import create_audio_backend
from adaptive_soundscape.audio.music_director import MusicDirector, config_from_settings
from adaptive_soundscape.audio.music_manifest import MusicIntensity
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
from adaptive_soundscape.core.ui_preferences import (
    UiPreferences,
    load_ui_preferences,
    save_ui_preferences,
)
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
from adaptive_soundscape.ui.main_window import MainWindow
from adaptive_soundscape.ui.settings_page import DEFAULT_STATUS_COLORS, SettingsPage

logger = logging.getLogger(__name__)

_MUSIC_STATE_LABELS = {
    MusicIntensity.CALM: "Calm",
    MusicIntensity.FOCUS: "Focus",
    MusicIntensity.DEEP_FOCUS: "Deep Focus",
    MusicIntensity.RECOVERY: "Recovery",
}


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
        self.director = MusicDirector(
            assets_dir=assets,
            backend=self.audio,
            config=config_from_settings(self.settings.adaptive_music),
        )
        self.window = MainWindow()
        self._manual_override = False
        self._current_context = WorkContext.UNKNOWN
        self._current_focus = FocusState.CALM_PRODUCTIVITY
        self._focus_score = 0.5
        self._audio_running = False
        self._active_profile_id = "unknown"

        self.user_mappings = load_user_mappings()
        self.inferer = ContextInferer(self.user_mappings)
        self._toast = self.window.inference_toast
        self._prompted_processes: set[str] = set()
        self._dismissed_processes: set[str] = set()
        self._last_process_key = ""

        # Sync initial volume with config / Settings page
        self.director.set_volume(self.settings.adaptive_music.master_volume)
        self.window.settings_page.set_volume(self.settings.adaptive_music.master_volume)
        self.window.settings_page.set_threshold(self.settings.cognitive.sensitivity)

        interval = self.settings.app.poll_interval_ms
        self._timer = QTimer()
        self._timer.setInterval(interval)
        self._timer.timeout.connect(self._tick)

        # ~60 Hz EQ-ring refresh (separate from the 1 Hz cognitive tick).
        self._viz_timer = QTimer()
        self._viz_timer.setInterval(16)
        self._viz_timer.timeout.connect(self._refresh_eq_bands)

        self.window.upload_page.set_assets_dir(assets)
        self.window.upload_page.soundtrack_changed.connect(self._on_albums_changed)

        self.window.home_page.action_toggled.connect(self._toggle_audio)
        self.window.categories_clicked.connect(self._open_category_editor)
        self.window.albums_clicked.connect(self._open_album_manager)
        self.window._override_check.toggled.connect(self._on_override)
        self.window._sensitivity_spin.valueChanged.connect(self._on_sensitivity)
        for chk in (self.window._title_check, self.window._process_check, self.window._log_check):
            chk.toggled.connect(self._on_privacy)

        self._toast.confirmed.connect(self._on_inference_confirmed)
        self._toast.dismissed.connect(self._on_inference_dismissed)

        # ── Settings page signals ──
        sp = self.window.settings_page
        sp.volume_changed.connect(self._on_volume_changed)
        sp.threshold_changed.connect(self._on_sensitivity)
        sp.waveform_smoothness_changed.connect(self._on_waveform_smoothness_changed)
        sp.aurora_brightness_gain_changed.connect(self._on_aurora_brightness_gain_changed)
        sp.main_theme_changed.connect(self._on_main_theme_changed)
        sp.categories_requested.connect(self._open_category_editor)
        sp.quit_requested.connect(QApplication.instance().quit)
        sp.reset_requested.connect(self._on_reset_settings)
        sp.status_colors_changed.connect(self._on_status_colors_changed)
        sp.dark_mode_toggled.connect(self._on_dark_mode_changed)

        self._ui_prefs = load_ui_preferences()
        self._main_theme = self._ui_prefs.main_theme or "unknown"
        self._status_colors = dict(DEFAULT_STATUS_COLORS)
        if self._ui_prefs.status_colors:
            self._status_colors.update(self._ui_prefs.status_colors)
        self._waveform_smoothness = float(self._ui_prefs.waveform_smoothness)
        self._aurora_brightness_gain = float(self._ui_prefs.aurora_brightness_gain)
        self._apply_ui_preferences()

        qt_app = QApplication.instance()
        if qt_app is not None:
            qt_app.aboutToQuit.connect(self._persist_user_state)

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
        self._persist_user_state()
        self._timer.stop()
        self._viz_timer.stop()
        self.monitor.stop()
        self.director.shutdown()
        self._toast.hide()

    def _persist_user_state(self) -> None:
        """Flush classification mappings and UI prefs to disk."""
        try:
            save_user_mappings(self.user_mappings)
        except OSError as exc:
            logger.warning("Failed to save user context mappings: %s", exc)
        try:
            prefs = UiPreferences(
                dark_mode=self.window.is_dark_mode,
                main_theme=self._main_theme,
                waveform_smoothness=self._waveform_smoothness,
                aurora_brightness_gain=self._aurora_brightness_gain,
                status_colors=dict(self._status_colors),
            )
            save_ui_preferences(prefs)
            self._ui_prefs = prefs
        except OSError as exc:
            logger.warning("Failed to save UI preferences: %s", exc)

    def _apply_ui_preferences(self) -> None:
        sp = self.window.settings_page
        sp.set_main_theme(self._main_theme)
        sp.set_status_colors(dict(self._status_colors))
        sp.set_waveform_smoothness(self._waveform_smoothness)
        self.window.home_page.set_waveform_smoothness(self._waveform_smoothness)
        sp.set_aurora_brightness_gain(self._aurora_brightness_gain)
        self.window.home_page.set_aurora_brightness_gain(self._aurora_brightness_gain)
        self.window._set_dark_mode(bool(self._ui_prefs.dark_mode))
        sp.set_dark_mode(bool(self._ui_prefs.dark_mode))

    def _refresh_eq_bands(self) -> None:
        if not self._audio_running:
            return
        bands = getattr(self.audio, "current_bands", None)
        if bands is None:
            bands = [0.0] * 48
        self.window.home_page.set_frequency_bands(list(bands))

    def _toggle_audio(self, _trigger: bool | None = None) -> None:
        if self._audio_running:
            self.director.pause()
            self._audio_running = False
            self._viz_timer.stop()
            self.window.home_page.set_running(False)
            self.window.set_status_message("")
            self._refresh_ui()
            return

        decision = self.transition.decide(
            self._current_context, self._current_focus, self._focus_score
        )
        try:
            self._bind_director_backend(self.audio)
            self.director.set_scenario(decision.profile_id, self._focus_score)
            self.director.set_parameters(decision.parameters)
            self.director.play()
        except Exception as exc:
            logger.exception("Failed to start audio backend")
            if self.settings.audio.fallback_to_placeholder:
                try:
                    assets = resolve_assets_dir(self.settings)
                    self.audio.stop()
                    self.audio = create_audio_backend(
                        self._placeholder_settings(), assets
                    )
                    self._bind_director_backend(self.audio)
                    self.director.set_scenario(decision.profile_id, self._focus_score)
                    self.director.set_parameters(decision.parameters)
                    self.director.play()
                    self.window.set_status_message(
                        "Using built-in audio mixer (Godot unavailable)."
                    )
                except Exception as fallback_exc:
                    logger.exception("Placeholder audio fallback failed")
                    self.window.set_status_message(f"Audio error: {fallback_exc}")
                    self.window.home_page.set_running(False)
                    return
            else:
                self.window.set_status_message(f"Audio error: {exc}")
                self.window.home_page.set_running(False)
                return
        self._audio_running = True
        self._active_profile_id = decision.profile_id
        self.window.home_page.set_running(True)
        self._viz_timer.start()
        self._refresh_eq_bands()
        self._publish_audio_params(decision)
        self._refresh_ui(decision.display_name)

    def _bind_director_backend(self, backend) -> None:
        self.director.backend = backend
        self.director.set_volume(self.settings.adaptive_music.master_volume)
        self.director.set_muted(False)

    def _placeholder_settings(self) -> Settings:
        """Return settings forced to the placeholder mixer backend."""
        return self.settings.model_copy(
            update={
                "audio": self.settings.audio.model_copy(update={"backend": "placeholder"})
            }
        )

    def _invalidate_audio_caches(self) -> None:
        invalidate = getattr(self.audio, "invalidate_caches", None)
        if callable(invalidate):
            invalidate()

    def _open_category_editor(self) -> None:
        updated = CategoryEditorDialog.edit(self.user_mappings, self.window)
        if updated is None:
            return
        self.user_mappings = updated
        self.inferer.set_user_mappings(updated)
        try:
            path = save_user_mappings(updated)
            self._prompted_processes.clear()
            self._dismissed_processes.clear()
            self.window.set_status_message(f"Category mappings saved to {path.name}.")
        except OSError as exc:
            logger.exception("Failed to save category mappings")
            self.window.set_status_message(f"Could not save categories: {exc}")

    def _open_album_manager(self) -> None:
        assets = resolve_assets_dir(self.settings)
        changed = AlbumManagerDialog.run(assets, self.window)
        if not changed:
            return
        self._invalidate_audio_caches()
        if self._audio_running:
            self.director.set_scenario(self._active_profile_id, self._focus_score)
        self.window.set_status_message(
            "Album updated. Intensity loops apply on the next music transition."
        )

    def _on_albums_changed(self) -> None:
        self._invalidate_audio_caches()
        if self._audio_running:
            self.director.set_scenario(self._active_profile_id, self._focus_score)

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

    def _on_volume_changed(self, value: float) -> None:
        """Handle master volume slider change from settings page."""
        self.audio.master_volume = value
        self.settings.audio.master_volume = value
        self.settings.adaptive_music.master_volume = value
        self.director.set_volume(value)

    def _on_main_theme_changed(self, theme: str) -> None:
        """Store the user-selected main/default theme preference."""
        self._main_theme = theme
        self._persist_user_state()
        logger.info("Main theme set to %s", theme)

    def _on_status_colors_changed(self, colors: dict[str, str]) -> None:
        """Store updated per-status colours from the settings page."""
        self._status_colors.update(colors)
        self._persist_user_state()
        logger.info("Status colours updated")

    def _on_waveform_smoothness_changed(self, value: float) -> None:
        self._waveform_smoothness = float(value)
        self.window.home_page.set_waveform_smoothness(self._waveform_smoothness)
        self._persist_user_state()

    def _on_aurora_brightness_gain_changed(self, value: float) -> None:
        self._aurora_brightness_gain = float(value)
        self.window.home_page.set_aurora_brightness_gain(self._aurora_brightness_gain)
        self._persist_user_state()

    def _on_dark_mode_changed(self, enabled: bool) -> None:
        del enabled
        self._persist_user_state()

    def _on_reset_settings(self) -> None:
        """Reset all settings to factory defaults."""
        defaults = Settings()
        self.settings.audio.master_volume = defaults.audio.master_volume
        self.settings.cognitive.sensitivity = defaults.cognitive.sensitivity
        self.audio.master_volume = defaults.audio.master_volume
        self.estimator.sensitivity = defaults.cognitive.sensitivity
        self._main_theme = "unknown"
        self._status_colors = dict(DEFAULT_STATUS_COLORS)
        self._waveform_smoothness = SettingsPage.DEFAULT_WAVEFORM_SMOOTHNESS
        self._aurora_brightness_gain = SettingsPage.DEFAULT_AURORA_BRIGHTNESS_GAIN
        self.window.settings_page.set_volume(defaults.audio.master_volume)
        self.window.settings_page.set_threshold(defaults.cognitive.sensitivity)
        self.window.settings_page.set_waveform_smoothness(
            SettingsPage.DEFAULT_WAVEFORM_SMOOTHNESS
        )
        self.window.home_page.set_waveform_smoothness(
            SettingsPage.DEFAULT_WAVEFORM_SMOOTHNESS
        )
        self.window.settings_page.set_aurora_brightness_gain(
            SettingsPage.DEFAULT_AURORA_BRIGHTNESS_GAIN
        )
        self.window.home_page.set_aurora_brightness_gain(
            SettingsPage.DEFAULT_AURORA_BRIGHTNESS_GAIN
        )
        self.window.settings_page.set_main_theme("unknown")
        self.window.settings_page.set_status_colors(dict(DEFAULT_STATUS_COLORS))
        self.director.set_volume(defaults.audio.master_volume)
        self.window.update_status_background("unknown")
        self._persist_user_state()
        logger.info("Settings reset to defaults")

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
        elif self._audio_running:
            # Intensity adapts continuously inside the active song.
            self.director.update_intensity(estimate.focus_score)
            self.director.set_parameters(decision.parameters)

        self._refresh_ui(decision.display_name)
        self.monitor.reset_window_switches()

        if self.settings.privacy.log_activity and self.settings.app.logging_enabled:
            logger.info(
                "activity context=%s focus=%.2f state=%s music=%s source=%s",
                ctx.value,
                estimate.focus_score,
                estimate.state.value,
                self.director.active_state.value,
                resolved.source,
            )

    def _maybe_prompt_misc(self, resolved) -> None:
        process_key = _process_key(resolved.process_name)
        if process_key != self._last_process_key:
            self._last_process_key = process_key

        if not resolved.needs_confirm or not resolved.is_misc:
            if self._toast.is_showing_for(resolved.process_name):
                self._toast.hide()
            return

        if not process_key:
            return
        if process_key in self._dismissed_processes:
            return
        if process_key in self._prompted_processes and self._toast.isVisible():
            return
        if process_key in self._prompted_processes and not self._toast.isVisible():
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
        key = _process_key(process_name)
        self.user_mappings.add_process(context, process_name or key)
        token = _distinctive_title_token(window_title)
        if token:
            self.user_mappings.add_title_keyword(context, token)
        try:
            save_user_mappings(self.user_mappings)
        except OSError as exc:
            logger.exception("Failed to persist window classification")
            self.window.set_status_message(f"Could not save classification: {exc}")
            return
        self.inferer.set_user_mappings(self.user_mappings)

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
        self._active_profile_id = decision.profile_id
        if self._audio_running:
            self.director.set_scenario(decision.profile_id, self._focus_score)
            self.director.set_parameters(decision.parameters)
            self.director.update_intensity(self._focus_score)
        self._publish_audio_params(decision)

    def _publish_audio_params(self, decision) -> None:
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
        state = self.director.active_state
        detail_parts = [f"Mode: {self.director.playback_mode}"]
        if self.director.active_song_id:
            detail_parts.append(f"Song: {self.director.active_song_id}")
        if self.director.playback_mode == "layered" and self.director.layer_gains:
            top = sorted(
                self.director.layer_gains.items(), key=lambda kv: kv[1], reverse=True
            )[:3]
            detail_parts.append(
                "Gains: " + ", ".join(f"{k}={v:.2f}" for k, v in top)
            )
        elif self.director.active_track_id:
            detail_parts.append(f"Loop: {self.director.active_track_id}")
        self.window.update_status(
            context=self._current_context,
            focus_state=self._current_focus,
            focus_score=self._focus_score,
            profile_name=profile_name,
            music_state=_MUSIC_STATE_LABELS.get(state, state.value),
            music_detail=" · ".join(detail_parts),
        )
        # Update background colour based on current status
        profile_id = self._current_context.value
        if profile_id in self._status_colors:
            self.window.update_status_background(profile_id)


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

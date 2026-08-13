"""Application orchestrator wiring all subsystems."""

from __future__ import annotations

import json
import logging
from pathlib import Path

# Silence all console logging — keep the terminal clean.
logging.getLogger().addHandler(logging.NullHandler())

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from adaptive_soundscape.activity.monitor import ActivityMonitor
from adaptive_soundscape.activity.window_tracker import list_open_windows
from adaptive_soundscape.audio.factory import create_audio_backend
from adaptive_soundscape.audio.music_director import MusicDirector, config_from_settings
from adaptive_soundscape.audio.music_manifest import MusicIntensity
from adaptive_soundscape.cognitive.estimator import FocusEstimate, FocusEstimator
from adaptive_soundscape.context.classifier import collect_unclassified, resolve_context
from adaptive_soundscape.context.inferer import ContextInferer
from adaptive_soundscape.context.persistence import ContextPersistence
from adaptive_soundscape.context.user_mappings import (
    load_user_mappings,
    save_user_mappings,
)
from adaptive_soundscape.core.bus import EventBus
from adaptive_soundscape.core.config import Settings, load_settings, resolve_assets_dir
from adaptive_soundscape.core.i18n import get_language as i18n_get_language
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
from adaptive_soundscape.focus_index.config import FocusIndexConfig
from adaptive_soundscape.focus_index.service import FocusIndexService
from adaptive_soundscape.session.calibration import CalibrationController
from adaptive_soundscape.session.pomodoro import PomodoroController, PomodoroPhase
from adaptive_soundscape.transition.controller import TransitionController
from adaptive_soundscape.ui.album_manager import AlbumManagerDialog
from adaptive_soundscape.ui.category_editor import CategoryEditorDialog
from adaptive_soundscape.ui.main_window import MainWindow
from adaptive_soundscape.ui.mini_overlay import MiniOverlay
from adaptive_soundscape.ui.probe_dialog import GoNoGoProbeDialog
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
        fli_cfg = self.settings.focus_index
        db_path = Path(fli_cfg.db_path)
        if not db_path.is_absolute():
            db_path = Path(__file__).resolve().parents[2] / db_path
        self.focus_index = FocusIndexService(
            config=FocusIndexConfig(
                window_seconds=fli_cfg.window_seconds,
                weight_alignment=fli_cfg.weight_alignment,
                weight_switch=fli_cfg.weight_switch,
                weight_idle=fli_cfg.weight_idle,
                weight_probe=fli_cfg.weight_probe,
                probe_ttl_minutes=fli_cfg.probe_ttl_minutes,
                retention_days=fli_cfg.retention_days,
                aligned_switch_penalty=fli_cfg.aligned_switch_penalty,
                recency_tau_seconds=fli_cfg.recency_tau_seconds,
                pattern_gate_low=fli_cfg.pattern_gate_low,
                pattern_assist_max=fli_cfg.pattern_assist_max,
                switch_rate_ref=getattr(fli_cfg, "switch_rate_ref", 1.25),
                short_burst_s=getattr(fli_cfg, "short_burst_s", 45.0),
                idle_threshold_s=getattr(fli_cfg, "idle_threshold_s", 45.0),
                db_path=db_path,
            ),
            db_path=db_path,
        )
        self.focus_index.smoothing = self.settings.cognitive.focus_smoothing
        self.focus_index.uncalibrated_smoothing = getattr(
            self.settings.cognitive, "uncalibrated_focus_smoothing", 0.18
        )
        self.focus_index.set_sensitivity(self.settings.cognitive.sensitivity)
        self.pomodoro = PomodoroController(
            work_minutes=self.settings.pomodoro.work_minutes,
            break_minutes=self.settings.pomodoro.break_minutes,
            session_calibration_minutes=self.settings.pomodoro.session_calibration_minutes,
            break_muffling=self.settings.muffling.break_muffling,
        )
        self.calibration = CalibrationController()
        self._muffling_strength = float(self.settings.muffling.strength)
        self._muffling_curve = float(
            getattr(self.settings.muffling, "curve_multiplier", 3.0)
        )
        self._probes_enabled = True
        self._debug_focus_override = False
        self._debug_focus_score = 0.6
        self._debug_layer_override = False
        self._classified_context = WorkContext.UNKNOWN
        self._auto_distract_active = False
        self._auto_distract_since = 0.0
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
        self._overlay = MiniOverlay()
        self._overlay.play_toggled.connect(self._toggle_audio)
        self._overlay.hide_requested.connect(self._overlay.hide)
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
        self._pending_classification: dict | None = None
        self._toast_manual = False
        self._seen_windows: dict[tuple[str, str], tuple[str, str]] = {}

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
        self.window.home_page.song_chosen.connect(self._on_song_chosen)
        self.window.home_page.pomodoro_start_requested.connect(self._on_pomodoro_start)
        self.window.home_page.pomodoro_cancel_requested.connect(self._on_pomodoro_cancel)
        self.window.home_page.calibrate_requested.connect(self._on_calibrate_requested)
        self.window.home_page.calibrate_cancel_requested.connect(
            self._on_calibrate_cancel
        )
        self.window.categories_clicked.connect(self._open_category_editor)
        self.window.albums_clicked.connect(self._open_album_manager)
        self.window._override_check.toggled.connect(self._on_override)
        self.window._sensitivity_spin.valueChanged.connect(self._on_sensitivity)
        for chk in (self.window._title_check, self.window._process_check, self.window._log_check):
            chk.toggled.connect(self._on_privacy)

        self._toast.confirmed.connect(self._on_inference_confirmed)
        self._toast.dismissed.connect(self._on_inference_dismissed)
        self.window.classification_panel.item_saved.connect(self._on_inference_confirmed)

        # Show unclassified-window list on the right (user clicks "Confirm Classification")
        self.window.home_page.classify_requested.connect(self._on_classify_requested)

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
        sp.muffling_strength_changed.connect(self._on_muffling_strength_changed)
        sp.muffling_curve_changed.connect(self._on_muffling_curve_changed)
        sp.intensity_smoothing_changed.connect(self._on_intensity_smoothing_changed)
        sp.gain_slew_changed.connect(self._on_gain_slew_changed)
        sp.focus_smoothing_changed.connect(self._on_focus_smoothing_changed)
        sp.scenario_crossfade_changed.connect(self._on_scenario_crossfade_changed)
        sp.probes_enabled_changed.connect(self._on_probes_enabled_changed)
        sp.probe_requested.connect(self._on_probe_requested)
        sp.export_focus_data_requested.connect(self._on_export_focus_data)
        sp.delete_focus_data_requested.connect(self._on_delete_focus_data)
        sp.debug_focus_override_changed.connect(self._on_debug_focus_override)
        sp.debug_layer_override_changed.connect(self._on_debug_layer_override)
        sp.debug_layer_gain_changed.connect(self._on_debug_layer_gain)
        sp.language_changed.connect(self._on_language_changed)
        self._ui_prefs = load_ui_preferences()
        self._main_theme = self._ui_prefs.main_theme or "unknown"
        self._status_colors = dict(DEFAULT_STATUS_COLORS)
        if self._ui_prefs.status_colors:
            self._status_colors.update(self._ui_prefs.status_colors)
        self._waveform_smoothness = float(self._ui_prefs.waveform_smoothness)
        self._aurora_brightness_gain = float(self._ui_prefs.aurora_brightness_gain)
        self._muffling_strength = float(self._ui_prefs.muffling_strength)
        self._muffling_curve = float(self._ui_prefs.muffling_curve)
        self.settings.muffling.curve_multiplier = self._muffling_curve
        if self._ui_prefs.intensity_smoothing is not None:
            alpha = float(self._ui_prefs.intensity_smoothing)
            self.settings.adaptive_music.intensity_smoothing = alpha
            self.director.config.intensity_smoothing = alpha
        if self._ui_prefs.gain_slew_seconds is not None:
            slew = float(self._ui_prefs.gain_slew_seconds)
            self.settings.adaptive_music.gain_slew_seconds = slew
            self.director.config.gain_slew_seconds = slew
            self.director._layer_mix.gain_slew_seconds = slew
        if self._ui_prefs.focus_smoothing is not None:
            fs = float(self._ui_prefs.focus_smoothing)
            self.settings.cognitive.focus_smoothing = fs
            self.focus_index.smoothing = fs
        if self._ui_prefs.scenario_crossfade_seconds is not None:
            xf = float(self._ui_prefs.scenario_crossfade_seconds)
            self.settings.adaptive_music.scenario_crossfade_seconds = xf
            self.director.config.scenario_crossfade_seconds = xf
            self.director.config.fallback_crossfade_seconds = xf
        self._probes_enabled = bool(self._ui_prefs.probes_enabled)
        self._language = self._ui_prefs.language or i18n_get_language()
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
        self._overlay.set_dark_mode(self.window.is_dark_mode)
        self._overlay.place_top_right()
        self._overlay.show()
        self._refresh_ui()

    def stop(self) -> None:
        self._persist_user_state()
        self._timer.stop()
        self._viz_timer.stop()
        self.monitor.stop()
        self.director.shutdown()
        self._toast.hide()
        self._overlay.hide()
        self._toast_manual = False
        self._pending_classification = None
        self.window.home_page.set_classify_available(False)
        self.window.classification_panel.hide_panel()

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
                muffling_strength=self._muffling_strength,
                muffling_curve=self._muffling_curve,
                intensity_smoothing=float(
                    self.settings.adaptive_music.intensity_smoothing
                ),
                gain_slew_seconds=float(
                    self.settings.adaptive_music.gain_slew_seconds
                ),
                focus_smoothing=float(self.settings.cognitive.focus_smoothing),
                scenario_crossfade_seconds=float(
                    self.settings.adaptive_music.scenario_crossfade_seconds
                ),
                probes_enabled=self._probes_enabled,
                status_colors=dict(self._status_colors),
                language=self._language,
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
        sp.set_muffling_strength(self._muffling_strength)
        sp.set_muffling_curve(self._muffling_curve)
        sp.set_intensity_smoothing(self.settings.adaptive_music.intensity_smoothing)
        sp.set_gain_slew(self.settings.adaptive_music.gain_slew_seconds)
        sp.set_focus_smoothing(self.settings.cognitive.focus_smoothing)
        sp.set_scenario_crossfade(
            self.settings.adaptive_music.scenario_crossfade_seconds
        )
        sp.set_probes_enabled(self._probes_enabled)
        self.window._set_dark_mode(bool(self._ui_prefs.dark_mode))
        sp.set_dark_mode(bool(self._ui_prefs.dark_mode))
        self.window.set_language(self._language)

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
            self._overlay.set_running(False)
            self.window.set_status_message("")
            self._refresh_ui()
            return

        ctx = (
            WorkContext.UNKNOWN
            if self.pomodoro.in_break
            else self._current_context
        )
        if self.pomodoro.in_break:
            decision = self.transition.force_profile(ctx, self._current_focus)
            self._current_context = ctx
        else:
            decision = self.transition.decide(
                ctx, self._current_focus, self._focus_score
            )
        params = self._apply_muffling_to_params(decision.parameters, self._focus_score)
        try:
            self._bind_director_backend(self.audio)
            self.director.set_scenario(decision.profile_id, self._focus_score)
            self.director.set_parameters(params)
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
                    self.director.set_parameters(params)
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
        self._overlay.set_running(True)
        self._viz_timer.start()
        self._refresh_eq_bands()
        self._publish_audio_params(decision, params)
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
        self._refresh_album_songs()

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
        self._overlay.set_dark_mode(bool(enabled))
        self._persist_user_state()

    def _on_language_changed(self, code: str) -> None:
        """Persist the new UI language and apply it across the window."""
        self._language = str(code)
        self.window.set_language(self._language)
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
        self._muffling_strength = SettingsPage.DEFAULT_MUFFLING_STRENGTH
        self._probes_enabled = True
        self._language = "en"
        self.window.set_language("en")
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
        self.window.settings_page.set_muffling_strength(self._muffling_strength)
        self.window.settings_page.set_probes_enabled(True)
        self.window.settings_page.set_main_theme("unknown")
        self.window.settings_page.set_status_colors(dict(DEFAULT_STATUS_COLORS))
        self.director.set_volume(defaults.audio.master_volume)
        self.window.update_status_background("unknown")
        self._persist_user_state()
        logger.info("Settings reset to defaults")

    def _on_sensitivity(self, value: float) -> None:
        self.estimator.sensitivity = value
        self.settings.cognitive.sensitivity = float(value)
        self.focus_index.smoothing = self.settings.cognitive.focus_smoothing
        self.focus_index.uncalibrated_smoothing = getattr(
            self.settings.cognitive, "uncalibrated_focus_smoothing", 0.18
        )
        self.focus_index.set_sensitivity(value)

    def _on_muffling_strength_changed(self, value: float) -> None:
        self._muffling_strength = max(0.0, min(1.0, float(value)))
        self.settings.muffling.strength = self._muffling_strength
        self._persist_user_state()

    def _on_muffling_curve_changed(self, value: float) -> None:
        self._muffling_curve = max(1.0, min(5.0, float(value)))
        self.settings.muffling.curve_multiplier = self._muffling_curve
        self._persist_user_state()

    def _on_intensity_smoothing_changed(self, value: float) -> None:
        alpha = max(0.05, min(0.90, float(value)))
        self.settings.adaptive_music.intensity_smoothing = alpha
        self.director.config.intensity_smoothing = alpha
        self._persist_user_state()

    def _on_gain_slew_changed(self, value: float) -> None:
        seconds = max(0.2, min(3.0, float(value)))
        self.settings.adaptive_music.gain_slew_seconds = seconds
        self.director.config.gain_slew_seconds = seconds
        self.director._layer_mix.gain_slew_seconds = seconds
        self._persist_user_state()

    def _on_focus_smoothing_changed(self, value: float) -> None:
        alpha = max(0.05, min(0.90, float(value)))
        self.settings.cognitive.focus_smoothing = alpha
        self.focus_index.smoothing = alpha
        self._persist_user_state()

    def _on_scenario_crossfade_changed(self, value: float) -> None:
        seconds = max(0.5, min(12.0, float(value)))
        self.settings.adaptive_music.scenario_crossfade_seconds = seconds
        self.director.config.scenario_crossfade_seconds = seconds
        self.director.config.fallback_crossfade_seconds = seconds
        self._persist_user_state()

    def _compute_muffling(self, focus_score: float) -> float:
        curve = max(1.0, float(self._muffling_curve))
        base = max(
            0.0,
            min(1.0, (1.0 - focus_score) * self._muffling_strength * curve),
        )
        override = self.pomodoro.muffling_override()
        if override is not None:
            # 1 + override → mixer applies the normal curve at (override)
            # then divides cutoff by 10 (about 10× more muffled than work).
            return 1.0 + max(0.0, min(1.0, override))
        return base

    def _update_auto_distraction(
        self, classified_ctx: WorkContext, focus_score: float
    ) -> WorkContext:
        """Override display/audio context to DISTRACTION when focus stays low.

        Classification for FLI ingest still uses ``classified_ctx``; only the
        effective UI/music context is overridden (avoids feedback loops).
        """
        cog = self.settings.cognitive
        if not getattr(cog, "auto_distraction_enabled", True):
            self._auto_distract_active = False
            return classified_ctx
        if self._manual_override:
            self._auto_distract_active = False
            return classified_ctx
        if self.calibration.force_aligned or self.pomodoro.in_session_calibration:
            self._auto_distract_active = False
            return classified_ctx

        import time as _time

        now = _time.monotonic()
        enter = float(getattr(cog, "auto_distraction_enter", 0.38))
        exit_ = float(getattr(cog, "auto_distraction_exit", 0.50))
        dwell = float(getattr(cog, "auto_distraction_dwell_seconds", 4.0))

        if self._auto_distract_active:
            if focus_score >= exit_:
                if dwell <= 0 or self._auto_distract_since <= 0:
                    if dwell <= 0:
                        self._auto_distract_active = False
                        self._auto_distract_since = 0.0
                    else:
                        self._auto_distract_since = now
                elif now - self._auto_distract_since >= dwell:
                    self._auto_distract_active = False
                    self._auto_distract_since = 0.0
            else:
                self._auto_distract_since = 0.0
        else:
            if focus_score <= enter:
                if dwell <= 0:
                    self._auto_distract_active = True
                    self._auto_distract_since = 0.0
                elif self._auto_distract_since <= 0:
                    self._auto_distract_since = now
                elif now - self._auto_distract_since >= dwell:
                    self._auto_distract_active = True
                    self._auto_distract_since = 0.0
            else:
                self._auto_distract_since = 0.0

        if self._auto_distract_active:
            return WorkContext.DISTRACTION
        return classified_ctx

    def _debug_mode_on(self) -> bool:
        return self._debug_focus_override or self._debug_layer_override

    def _sync_debug_songs(self) -> None:
        """Debug mixes stay out of rotation unless Settings debug is on."""
        self.director.set_include_debug_songs(self._debug_mode_on())
        self._refresh_album_songs()

    def _refresh_album_songs(self) -> None:
        self.window.home_page.set_album_songs(
            self.director.album_song_ids(),
            self.director.active_song_id,
        )

    def _on_song_chosen(self, song_id: str) -> None:
        self.director.set_song(song_id, focus_score=self._focus_score)
        self._refresh_ui()

    def _on_debug_focus_override(self, enabled: bool, score: float) -> None:
        self._debug_focus_override = bool(enabled)
        self._debug_focus_score = max(0.0, min(1.0, float(score)))
        self._sync_debug_songs()
        if self._debug_focus_override and self._audio_running:
            # Snap director smoothing so the audition responds immediately.
            self.director.force_intensity(self._debug_focus_score)

    def _on_debug_layer_override(self, enabled: bool) -> None:
        self._debug_layer_override = bool(enabled)
        gains = getattr(self.window.settings_page, "_debug_layer_gains", None)
        self.director.set_debug_layer_override(
            self._debug_layer_override,
            dict(gains) if isinstance(gains, dict) else None,
        )
        self._sync_debug_songs()

    def _on_debug_layer_gain(self, layer_id: str, gain: float) -> None:
        self.director.set_debug_layer_gain(layer_id, gain)

    def _on_probes_enabled_changed(self, enabled: bool) -> None:
        self._probes_enabled = bool(enabled)
        self._persist_user_state()

    def _on_pomodoro_start(self, task_profile: str) -> None:
        prev = self.pomodoro.state.phase
        state = self.pomodoro.start_work(task_profile or "unknown")
        self._on_pomodoro_phase_changed(prev, state.phase)
        self.focus_index.set_task_profile(state.task_profile)
        if self.pomodoro.in_session_calibration:
            self.calibration.start_session(state.task_profile, minutes=5.0)
            self.focus_index.set_calibration_mode(True, force_aligned=True)
        self.window.home_page.set_pomodoro_active(True, label="End Pomodoro")
        self.window.home_page.set_pomodoro_progress(
            self.pomodoro.state.remaining_fraction, active=True
        )
        self._overlay.set_pomodoro(
            active=True,
            remaining_seconds=self.pomodoro.state.remaining_seconds,
        )
        self.window.set_status_message(
            state.notice or f"Pomodoro work started ({state.task_profile})."
        )

    def _on_pomodoro_cancel(self) -> None:
        prev = self.pomodoro.state.phase
        self.pomodoro.cancel()
        self._on_pomodoro_phase_changed(prev, PomodoroPhase.IDLE)
        self.focus_index.set_calibration_mode(False)
        self.calibration.cancel()
        self.focus_index.storage.delete_session_patterns()
        self.window.home_page.set_pomodoro_active(False)
        self._overlay.set_pomodoro(active=False)
        self.window.set_status_message("Pomodoro ended.")

    def _on_pomodoro_phase_changed(
        self, previous: PomodoroPhase, current: PomodoroPhase
    ) -> None:
        work_phases = {PomodoroPhase.WORK, PomodoroPhase.SESSION_CALIBRATION}
        if current == PomodoroPhase.BREAK and previous != PomodoroPhase.BREAK:
            self._play_pomodoro_chime("break")
            self._apply_break_music()
            return
        if current in work_phases and previous not in work_phases:
            self._play_pomodoro_chime("work")
            if previous == PomodoroPhase.BREAK:
                self._restore_music_after_break()
            return
        if current == PomodoroPhase.IDLE and previous == PomodoroPhase.BREAK:
            self._restore_music_after_break()

    def _play_pomodoro_chime(self, kind: str) -> None:
        player = getattr(self.audio, "play_notification", None)
        if self._audio_running and callable(player):
            try:
                player(kind)
                return
            except Exception:
                logger.exception("Pomodoro %s chime via mixer failed", kind)
        from adaptive_soundscape.audio.chimes import play_chime_standalone

        play_chime_standalone(kind, self.settings.audio.sample_rate)

    def _apply_break_music(self) -> None:
        """Force the Neutral (unknown) album for the whole break."""
        decision = self.transition.force_profile(
            WorkContext.UNKNOWN, self._current_focus
        )
        self._current_context = WorkContext.UNKNOWN
        if self._audio_running:
            self._apply_audio(decision)

    def _restore_music_after_break(self) -> None:
        ctx = self._classified_context
        if not self._manual_override:
            ctx = self._update_auto_distraction(ctx, self._focus_score)
        decision = self.transition.force_profile(ctx, self._current_focus)
        self._current_context = ctx
        if self._audio_running:
            self._apply_audio(decision)

    def _on_calibrate_requested(self, task_profile: str) -> None:
        profile = task_profile or "unknown"
        state = self.calibration.start_dedicated(profile, minutes=8.0)
        self.focus_index.set_task_profile(profile)
        self.focus_index.set_calibration_mode(True, force_aligned=True)
        self.window.home_page.set_calibration_active(True, label="Cancel Calibration")
        self.window.set_status_message(state.notice)

    def _on_calibrate_cancel(self) -> None:
        self.calibration.cancel()
        self.focus_index.set_calibration_mode(False)
        self.window.home_page.set_calibration_active(False)
        self.window.set_status_message("Calibration cancelled.")

    def _on_probe_requested(self) -> None:
        if not self._probes_enabled:
            self.window.set_status_message("Attention probes are disabled in Settings.")
            return
        profile = self.focus_index.bridge.task_profile
        event = GoNoGoProbeDialog.run(self.window, task_profile=profile)
        if event is None:
            return
        self.focus_index.record_probe(event)
        self.window.set_status_message(
            f"Probe recorded — accuracy {event.accuracy:.0%}."
        )

    def _on_export_focus_data(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self.window,
            "Export Focus Data",
            "focus_index_export.json",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            data = self.focus_index.export_data()
            Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
            self.window.set_status_message(f"Exported focus data to {Path(path).name}.")
        except OSError as exc:
            self.window.set_status_message(f"Export failed: {exc}")

    def _on_delete_focus_data(self) -> None:
        reply = QMessageBox.question(
            self.window,
            "Delete Focus Data",
            "Delete all local focus events, aggregates, and calibration patterns?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.focus_index.delete_all_data()
        self.window.set_status_message("Focus data deleted.")

    def _apply_muffling_to_params(self, params, focus_score: float):
        return params.with_muffling(self._compute_muffling(focus_score))

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
            classified = self.window.manual_context
            confidence = 1.0
        else:
            classified = self.persistence.update(resolved.context, resolved.confidence)
            confidence = resolved.confidence
            self._maybe_prompt_misc(resolved)
            self._update_classify_button(resolved)
        self._classified_context = classified

        # Pomodoro / calibration bookkeeping before scoring.
        prev_pomo = self.pomodoro.state.phase
        pomo = self.pomodoro.tick()
        if pomo.phase != prev_pomo:
            self._on_pomodoro_phase_changed(prev_pomo, pomo.phase)
        calib_state, calib_done = self.calibration.tick()
        if calib_done:
            kind = self.calibration.last_completed_kind
            scope = "session" if kind and kind.value == "session" else "dedicated"
            try:
                self.focus_index.save_calibration_pattern(
                    task_profile=calib_state.task_profile or classified.value,
                    scope=scope,
                    window_seconds=max(60.0, calib_state.duration_minutes * 60.0),
                )
            except Exception:
                logger.exception("Failed to save calibration pattern")
            self.focus_index.set_calibration_mode(False)
            self.window.home_page.set_calibration_active(False)
            self.window.set_status_message(calib_state.notice or "Calibration complete.")
        elif self.calibration.force_aligned or self.pomodoro.in_session_calibration:
            self.focus_index.set_calibration_mode(True, force_aligned=True)
        else:
            self.focus_index.set_calibration_mode(False)

        # Score using the classified (real) context — not the auto-distract override.
        if self._debug_focus_override:
            score = self._debug_focus_score
            if score >= 0.82:
                state = FocusState.DEEP_FOCUS
            elif score >= 0.45:
                state = FocusState.CALM_PRODUCTIVITY
            else:
                state = FocusState.MILD_DISTRACTION
            estimate = FocusEstimate(focus_score=score, state=state, raw_score=score)
        elif self.settings.focus_index.enabled:
            estimate = self.focus_index.estimate_for_app(
                snapshot, classified, interval_s=interval
            )
        else:
            from adaptive_soundscape.cognitive.signals import FocusSignals

            metrics = self.monitor.metrics(snapshot, interval)
            signals = FocusSignals(
                input_rate=metrics.input_rate,
                switch_rate=metrics.switch_rate,
                idle_ratio=metrics.idle_ratio,
                cpu_load=metrics.cpu_load,
                context=classified,
                context_confidence=confidence,
            )
            estimate = self.estimator.estimate(signals)

        if estimate.state != self._current_focus or abs(estimate.focus_score - self._focus_score) > 0.01:
            self.bus.publish(FocusUpdated(estimate.focus_score, estimate.state))
        self._current_focus = estimate.state
        self._focus_score = estimate.focus_score

        # Low focus → auto DISTRACTION for UI/music only (hysteresis + dwell).
        effective = self._update_auto_distraction(classified, estimate.focus_score)
        if self.pomodoro.in_break:
            effective = WorkContext.UNKNOWN
        if effective != self._current_context:
            self.bus.publish(
                ContextChanged(self._current_context, effective, confidence)
            )
            self._current_context = effective
            if self._auto_distract_active and effective == WorkContext.DISTRACTION:
                self.window.set_status_message(
                    "Low focus — recovery soundscape (auto-distraction)."
                )

        decision = self.transition.decide(
            effective, estimate.state, estimate.focus_score
        )
        params = self._apply_muffling_to_params(decision.parameters, estimate.focus_score)
        if decision.should_transition and self._audio_running:
            self._apply_audio(decision)
        elif self._audio_running:
            # Intensity adapts continuously inside the active song.
            if self._debug_focus_override:
                self.director.force_intensity(estimate.focus_score)
            else:
                self.director.update_intensity(estimate.focus_score)
            self.director.set_parameters(params)

        # Periodic retention purge (cheap; once per ~hour of ticks).
        if not hasattr(self, "_purge_counter"):
            self._purge_counter = 0
        self._purge_counter += 1
        if self._purge_counter >= 3600:
            self._purge_counter = 0
            try:
                self.focus_index.purge()
            except Exception:
                logger.exception("Focus index purge failed")

        if self.pomodoro.state.is_active:
            remaining = int(self.pomodoro.state.remaining_seconds)
            mm, ss = divmod(remaining, 60)
            phase = self.pomodoro.state.phase.value.replace("_", " ")
            self.window.home_page.set_pomodoro_active(
                True, label=f"End · {mm:02d}:{ss:02d}"
            )
            self.window.home_page.set_pomodoro_progress(
                self.pomodoro.state.remaining_fraction, active=True
            )
            self._overlay.set_pomodoro(
                active=True,
                remaining_seconds=self.pomodoro.state.remaining_seconds,
            )
            self.window.set_status_message(
                f"Pomodoro {phase}: {mm:02d}:{ss:02d}"
                + (f" — {self.pomodoro.state.notice}" if self.pomodoro.state.notice else "")
            )
        else:
            self.window.home_page.set_pomodoro_active(False)
            self._overlay.set_pomodoro(active=False)
        if self.calibration.state.active and not self.pomodoro.state.is_active:
            remaining = int(self.calibration.state.remaining_seconds)
            mm, ss = divmod(remaining, 60)
            self.window.home_page.set_calibration_active(
                True, label=f"Cancel · {mm:02d}:{ss:02d}"
            )
            self.window.set_status_message(
                f"{self.calibration.state.notice} ({mm:02d}:{ss:02d} left)"
            )
        elif not self.calibration.state.active:
            self.window.home_page.set_calibration_active(False)

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
        """Hide the toast if user switches away from a misc-unclassified window."""
        process_key = _process_key(resolved.process_name)
        if process_key != self._last_process_key:
            self._last_process_key = process_key

        # Don't touch a toast the user opened manually — let them dismiss it.
        if self._toast_manual:
            return

        # Toast auto-hides when the current window is no longer misc/unclassified.
        if not resolved.needs_confirm or not resolved.is_misc:
            if self._toast.is_showing_for(resolved.process_name):
                self._toast.hide()
            return

    def _update_classify_button(self, resolved) -> None:
        """Keep Confirm Classification visible during playback and remember misc windows."""
        process_key = _process_key(resolved.process_name)
        suggested = resolved.context
        confidence = resolved.confidence
        source = resolved.source
        if resolved.inference is not None and resolved.inference.context != WorkContext.UNKNOWN:
            suggested = resolved.inference.context
            confidence = resolved.inference.confidence
            source = resolved.inference.source

        self._pending_classification = {
            "process_name": resolved.process_name,
            "window_title": resolved.window_title,
            "process_key": process_key,
            "suggested": suggested,
            "confidence": confidence,
            "source": source,
        }
        cache_key = (process_key, (resolved.window_title or "").lower())
        own_title = (self.window.windowTitle() or "").lower()
        is_own = (resolved.window_title or "").lower() == own_title and bool(own_title)
        if resolved.needs_confirm and not is_own:
            self._seen_windows[cache_key] = (
                resolved.process_name,
                resolved.window_title,
            )
        else:
            self._seen_windows.pop(cache_key, None)
        self.window.home_page.set_classify_available(True)

    def _collect_unclassified_windows(self) -> list[dict]:
        pairs: list[tuple[str, str]] = []
        try:
            for info in list_open_windows():
                pairs.append((info.process_name, info.title))
        except Exception:
            logger.exception("Failed to enumerate open windows")
        pairs.extend(self._seen_windows.values())
        own_title = (self.window.windowTitle() or "").lower()
        if own_title:
            pairs = [
                (proc, title)
                for proc, title in pairs
                if (title or "").lower() != own_title
            ]
        resolved = collect_unclassified(
            pairs,
            user_mappings=self.user_mappings,
            inferer=self.inferer,
        )
        items: list[dict] = []
        for item in resolved:
            suggested = item.context
            confidence = item.confidence
            source = item.source
            if item.inference is not None and item.inference.context != WorkContext.UNKNOWN:
                suggested = item.inference.context
                confidence = item.inference.confidence
                source = item.inference.source
            items.append(
                {
                    "process_name": item.process_name,
                    "window_title": item.window_title,
                    "suggested": suggested,
                    "confidence": confidence,
                    "source": source,
                }
            )
        return items

    def _on_classify_requested(self) -> None:
        """Open the right-side list of unclassified windows."""
        self._toast.hide()
        self._toast_manual = False
        panel = self.window.classification_panel
        items = self._collect_unclassified_windows()
        panel.set_items(items)
        panel.show_panel()
        if items:
            self.window.set_status_message(
                f"{len(items)} unclassified window(s) — save each one on the right."
            )
        else:
            self.window.set_status_message("No unclassified windows right now.")

    def _on_inference_confirmed(
        self, process_name: str, window_title: str, context: object
    ) -> None:
        self._toast_manual = False
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
        self._seen_windows = {
            k: v for k, v in self._seen_windows.items() if k[0] != key
        }

        label = context.value.replace("_", " ")
        self.window.set_status_message(f"Saved '{process_name or key}' → {label}.")

        if self.window.classification_panel.isVisible():
            remaining = self._collect_unclassified_windows()
            self.window.classification_panel.set_items(remaining)

        if key == self._last_process_key:
            self.persistence.force(context)
            self._current_context = context
            decision = self.transition.force_profile(context, self._current_focus)
            if self._audio_running:
                self._apply_audio(decision)
            self._refresh_ui(decision.display_name)

    def _on_inference_dismissed(self, process_key: str) -> None:
        self._toast_manual = False
        if process_key:
            self._dismissed_processes.add(process_key)

    def _apply_audio(self, decision) -> None:
        self._active_profile_id = decision.profile_id
        params = self._apply_muffling_to_params(decision.parameters, self._focus_score)
        if self._audio_running:
            self.director.set_scenario(decision.profile_id, self._focus_score)
            self.director.set_parameters(params)
            self.director.update_intensity(self._focus_score)
        self._publish_audio_params(decision, params)

    def _publish_audio_params(self, decision, params=None) -> None:
        p = params if params is not None else decision.parameters
        self.bus.publish(
            AudioParametersUpdated(
                profile_id=decision.profile_id,
                brightness=p.brightness,
                energy=p.energy,
                warmth=p.warmth,
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
        self._overlay.set_focus(self._focus_score)
        self._overlay.set_running(self._audio_running)
        self._overlay.set_dark_mode(self.window.is_dark_mode)
        self._refresh_album_songs()


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

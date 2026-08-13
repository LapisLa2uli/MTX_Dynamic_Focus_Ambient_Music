"""Settings page — theme, audio, cognitive, and personalization controls."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from adaptive_soundscape.audio.layer_mix import LAYER_IDS
from adaptive_soundscape.core.events import WorkContext
from adaptive_soundscape.core.i18n import (
    SUPPORTED_LANGUAGES,
    set_language as i18n_set_language,
    status_label as i18n_status_label,
    theme_label as i18n_theme_label,
    tr,
)
from adaptive_soundscape.ui.icons import build_profile_icons


class _ClickOnlySlider(QSlider):
    """A slider whose value is changed by clicking/dragging, not the wheel.

    The settings page lives in a scroll area; a plain slider would steal
    the mouse wheel when the cursor happens to hover over it, so scrolling
    the page would randomly move sliders. Wheel events are therefore
    ignored here and propagate to the scroll area instead.
    """

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()


class _ClickOnlyComboBox(QComboBox):
    """A combo box that only changes when clicked open, never via the wheel.

    Same rationale as :class:`_ClickOnlySlider`: hovering a combo while
    scrolling the settings page must not silently change the selection.
    """

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()


# ---------------------------------------------------------------------------
# Stylesheets
# ---------------------------------------------------------------------------
SETTINGS_STYLE = """
QWidget#settingsPage {
    background-color: #1a1a1e;
}
QScrollArea#settingsScroll {
    background: transparent;
    border: none;
}
QWidget#scrollContent {
    background: transparent;
}
QLabel#sectionTitle {
    color: #8888a0;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    padding-top: 20px;
}
QLabel#settingLabel {
    color: #c8c8d8;
    font-size: 14px;
    font-weight: 700;
}
QLabel#valueLabel {
    color: #5b8def;
    font-size: 14px;
    font-weight: 700;
    min-width: 42px;
}
QLabel#hintLabel {
    color: #686878;
    font-size: 12px;
    font-weight: 400;
    padding-left: 2px;
}
QLabel#aboutLabel {
    color: #a8a8b8;
    font-size: 13px;
    font-weight: 400;
    line-height: 1.45;
    padding: 4px 2px 8px 2px;
}
QSlider::groove:horizontal {
    background: #2e2e36;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #5b8def;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background: #7baef4;
}
QSlider::sub-page:horizontal {
    background: #5b8def;
    border-radius: 3px;
}
QComboBox {
    background-color: #25252b;
    border: 1px solid #44444d;
    border-radius: 6px;
    padding: 6px 12px;
    color: #e8e8ec;
    font-size: 14px;
    font-weight: 700;
    min-width: 180px;
}
QComboBox:hover { border-color: #5b8def; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background-color: #25252b;
    border: 1px solid #44444d;
    color: #e8e8ec;
    selection-background-color: #3a3a4a;
}
"""

LIGHT_SETTINGS_STYLE = """
QWidget#settingsPage {
    background-color: #f5f5f8;
}
QScrollArea#settingsScroll {
    background: transparent;
    border: none;
}
QWidget#scrollContent {
    background: transparent;
}
QLabel#sectionTitle {
    color: #707080;
    font-size: 12px;
    font-weight: 700;
    padding-top: 20px;
}
QLabel#settingLabel {
    color: #2a2a38;
    font-size: 14px;
    font-weight: 700;
}
QLabel#valueLabel {
    color: #3d6fd4;
    font-size: 14px;
    font-weight: 700;
    min-width: 42px;
}
QLabel#hintLabel {
    color: #808090;
    font-size: 12px;
    font-weight: 400;
    padding-left: 2px;
}
QLabel#aboutLabel {
    color: #505060;
    font-size: 13px;
    font-weight: 400;
    line-height: 1.45;
    padding: 4px 2px 8px 2px;
}
QSlider::groove:horizontal {
    background: #d8d8e0;
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #5b8def;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background: #3d6fd4;
}
QSlider::sub-page:horizontal {
    background: #5b8def;
    border-radius: 3px;
}
QComboBox {
    background-color: #ffffff;
    border: 1px solid #c0c0c8;
    border-radius: 6px;
    padding: 6px 12px;
    color: #1a1a1e;
    font-size: 14px;
    font-weight: 700;
    min-width: 180px;
}
QComboBox:hover { border-color: #5b8def; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #c0c0c8;
    color: #1a1a1e;
    selection-background-color: #d0d8f0;
}
"""

TOGGLE_ON_STYLE = """
QPushButton {
    background-color: #5b8def;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 700;
}
QPushButton:hover { background-color: #6ca4f4; }
"""

TOGGLE_OFF_STYLE = """
QPushButton {
    background-color: #3a3a44;
    color: #88889a;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-size: 13px;
    font-weight: 700;
}
QPushButton:hover { background-color: #4a4a55; }
"""

ACTION_BTN_STYLE = """
QPushButton {
    background-color: #2a2a34;
    border: 1px solid #3e3e4a;
    border-radius: 6px;
    color: #c0c0d0;
    font-size: 12px;
    font-weight: 700;
    padding: 10px 20px;
}
QPushButton:hover {
    background-color: #333340;
    color: #e8e8ec;
}
"""

ACTION_BTN_WHITE_STYLE = """
QPushButton {
    background-color: #2a2a34;
    border: 1px solid #3e3e4a;
    border-radius: 6px;
    color: #ffffff;
    font-size: 12px;
    font-weight: 700;
    padding: 10px 20px;
}
QPushButton:hover {
    background-color: #333340;
    color: #ffffff;
}
"""

ACTION_BTN_LIGHT_STYLE = """
QPushButton {
    background-color: #e8e8ee;
    border: 1px solid #c0c0c8;
    border-radius: 6px;
    color: #404050;
    font-size: 12px;
    font-weight: 700;
    padding: 10px 20px;
}
QPushButton:hover {
    background-color: #d8d8e0;
    color: #181820;
}
"""

QUIT_BTN_STYLE = """
QPushButton {
    background-color: #4a2a2a;
    border: 1px solid #5a3a3a;
    border-radius: 6px;
    color: #e08888;
    font-size: 12px;
    font-weight: 700;
    padding: 10px 20px;
}
QPushButton:hover {
    background-color: #5a3a3a;
    color: #f0a0a0;
}
"""

QUIT_BTN_LIGHT_STYLE = """
QPushButton {
    background-color: #f0d8d8;
    border: 1px solid #d0b0b0;
    border-radius: 6px;
    color: #a04040;
    font-size: 12px;
    font-weight: 700;
    padding: 10px 20px;
}
QPushButton:hover {
    background-color: #e8c8c8;
    color: #801818;
}
"""

TITLE_STYLE = """
QLabel#pageTitle {
    color: #e8e8ec;
    font-size: 20px;
    font-weight: 700;
    padding-bottom: 6px;
}
"""

LIGHT_TITLE_STYLE = """
QLabel#pageTitle {
    color: #1a1a1e;
    font-size: 20px;
    font-weight: 700;
    padding-bottom: 6px;
}
"""

# Rainbow defaults — one colour per cognitive status
DEFAULT_STATUS_COLORS: dict[str, str] = {
    "programming":     "#61afef",
    "team_workflow":   "#98c379",
    "reading_writing": "#e5c07b",
    "scientific":      "#56b6c2",
    "creative_design": "#c678dd",
    "distraction":     "#e06c75",
    "unknown":         "#abb2bf",
}

STATUS_DISPLAY_NAMES: dict[str, str] = {
    "programming":     "Deep Code",
    "team_workflow":   "Collaborative",
    "reading_writing": "Quiet Study",
    "scientific":      "Lab Focus",
    "creative_design": "Creative Flow",
    "distraction":     "Recovery",
    "unknown":         "Neutral",
}

COLOR_PICKER_BTN_STYLE = """
QPushButton {
    background-color: #333340;
    color: #c8c8d4;
    border: 1px solid #4a4a58;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 12px;
}
QPushButton:hover {
    background-color: #444458;
    color: #e8e8ec;
}
"""

LIGHT_COLOR_PICKER_BTN_STYLE = """
QPushButton {
    background-color: #e0e0e8;
    color: #383848;
    border: 1px solid #b0b0b8;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 12px;
}
QPushButton:hover {
    background-color: #d0d0d8;
    color: #101018;
}
"""


class SettingsPage(QWidget):
    """Settings page with theme toggle, volume, threshold, theme picker.

    Signals
    -------
    dark_mode_toggled : bool
    volume_changed : float         0.0 – 1.0
    threshold_changed : float      0.2 – 2.0  (sensitivity)
    main_theme_changed : str       WorkContext value
    quit_requested
    reset_requested
    home_requested
    """

    dark_mode_toggled = pyqtSignal(bool)
    volume_changed = pyqtSignal(float)
    threshold_changed = pyqtSignal(float)
    waveform_smoothness_changed = pyqtSignal(float)
    aurora_brightness_gain_changed = pyqtSignal(float)
    main_theme_changed = pyqtSignal(str)
    quit_requested = pyqtSignal()
    reset_requested = pyqtSignal()
    home_requested = pyqtSignal()
    categories_requested = pyqtSignal()
    status_colors_changed = pyqtSignal(dict)
    muffling_strength_changed = pyqtSignal(float)
    muffling_curve_changed = pyqtSignal(float)
    intensity_smoothing_changed = pyqtSignal(float)
    gain_slew_changed = pyqtSignal(float)
    focus_smoothing_changed = pyqtSignal(float)
    scenario_crossfade_changed = pyqtSignal(float)
    probes_enabled_changed = pyqtSignal(bool)
    probe_requested = pyqtSignal()
    export_focus_data_requested = pyqtSignal()
    delete_focus_data_requested = pyqtSignal()
    debug_focus_override_changed = pyqtSignal(bool, float)  # enabled, score 0–1
    debug_layer_override_changed = pyqtSignal(bool)
    debug_layer_gain_changed = pyqtSignal(str, float)  # layer_id, gain 0–1
    language_changed = pyqtSignal(str)

    DEFAULT_WAVEFORM_SMOOTHNESS = 0.35
    DEFAULT_AURORA_BRIGHTNESS_GAIN = 1.5
    DEFAULT_MUFFLING_STRENGTH = 0.65
    LAYER_LABELS: dict[str, str] = {
        "pad": "Pad",
        "harmony": "Harmony",
        "melody_a": "Melody A",
        "rhythm": "Rhythm",
        "melody_b": "Melody B",
        "texture": "Texture",
        "recovery": "Recovery",
    }

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        master_volume: float = 0.75,
        sensitivity: float = 1.0,
        main_theme: str = "unknown",
        waveform_smoothness: float = DEFAULT_WAVEFORM_SMOOTHNESS,
        aurora_brightness_gain: float = DEFAULT_AURORA_BRIGHTNESS_GAIN,
        muffling_strength: float = DEFAULT_MUFFLING_STRENGTH,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._dark = True
        self._status_colors: dict[str, str] = dict(DEFAULT_STATUS_COLORS)
        self._trans: list[tuple[str, QWidget]] = []
        self._color_labels: dict[str, QLabel] = {}
        self._color_icon_labels: dict[str, QLabel] = {}
        self._color_icons = {
            "dark": build_profile_icons("#a8a8bc"),
            "light": build_profile_icons("#56566e"),
        }

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 28, 40, 24)
        outer.setSpacing(0)

        # ── Title ──
        self._title = QLabel(tr("settings_title"))
        self._title.setObjectName("pageTitle")
        outer.addWidget(self._title)
        self._trans.append(("settings_title", self._title))

        # ── Scrollable content area ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("settingsScroll")

        scroll_content = QWidget()
        scroll_content.setObjectName("scrollContent")
        content = QVBoxLayout(scroll_content)
        content.setContentsMargins(0, 8, 0, 8)
        content.setSpacing(12)

        # -- Section: About --
        content.addWidget(self._section_label("section_about"))
        about = QLabel(tr("about_text"))
        about.setObjectName("aboutLabel")
        about.setWordWrap(True)
        about.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        content.addWidget(about)
        self._trans.append(("about_text", about))

        # -- Section: Appearance --
        content.addWidget(self._section_label("section_appearance"))
        self._build_dark_mode_row(content)
        self._build_language_row(content)
        self._wave_slider, self._wave_label = self._build_slider_row(
            content,
            "wave_label",
            int(round(waveform_smoothness * 100)),
            0,
            100,
            "{:d}%",
        )
        wave_hint = QLabel(tr("wave_hint"))
        wave_hint.setObjectName("hintLabel")
        content.addWidget(wave_hint)
        self._trans.append(("wave_hint", wave_hint))

        self._aurora_slider, self._aurora_label = self._build_slider_row(
            content,
            "aurora_label",
            int(round(aurora_brightness_gain * 100)),
            0,
            300,
            "{:.1f}×",
        )
        aurora_hint = QLabel(tr("aurora_hint"))
        aurora_hint.setObjectName("hintLabel")
        content.addWidget(aurora_hint)
        self._trans.append(("aurora_hint", aurora_hint))

        # -- Section: Audio --
        content.addWidget(self._section_label("section_audio"))
        self._volume_slider, self._volume_label = self._build_slider_row(
            content, "volume_label", int(master_volume * 100), 0, 100, "{:d}%"
        )
        self._muffle_slider, self._muffle_label = self._build_slider_row(
            content,
            "muffle_label",
            int(round(muffling_strength * 100)),
            0,
            100,
            "{:d}%",
        )
        muffle_hint = QLabel(tr("muffle_hint"))
        muffle_hint.setObjectName("hintLabel")
        muffle_hint.setWordWrap(True)
        content.addWidget(muffle_hint)
        self._trans.append(("muffle_hint", muffle_hint))

        # Effect response (sensitivities)
        content.addWidget(self._section_label("section_effects"))
        self._muffle_curve_slider, self._muffle_curve_label = self._build_slider_row(
            content,
            "muffle_curve_label",
            int(round(3.0 * 100)),
            100,
            500,
            "{:.1f}×",
        )
        self._intensity_smooth_slider, self._intensity_smooth_label = self._build_slider_row(
            content,
            "intensity_smooth_label",
            int(round(0.35 * 100)),
            5,
            90,
            "{:.2f}",
        )
        self._gain_slew_slider, self._gain_slew_label = self._build_slider_row(
            content,
            "gain_slew_label",
            int(round(1.0 * 100)),
            20,
            300,
            "{:.1f}s",
        )
        self._focus_smooth_slider, self._focus_smooth_label = self._build_slider_row(
            content,
            "focus_smooth_label",
            int(round(0.40 * 100)),
            5,
            90,
            "{:.2f}",
        )
        self._scenario_xfade_slider, self._scenario_xfade_label = self._build_slider_row(
            content,
            "scenario_xfade_label",
            int(round(4.0 * 100)),
            50,
            1200,
            "{:.1f}s",
        )
        effects_hint = QLabel(tr("effects_hint"))
        effects_hint.setObjectName("hintLabel")
        effects_hint.setWordWrap(True)
        content.addWidget(effects_hint)
        self._trans.append(("effects_hint", effects_hint))

        # -- Section: Cognitive --
        content.addWidget(self._section_label("section_cognitive"))
        self._threshold_slider, self._threshold_label = self._build_slider_row(
            content,
            "threshold_label",
            int(sensitivity * 100),
            20,
            200,
            "{:.1f}",
        )
        hint = QLabel(tr("threshold_hint"))
        hint.setObjectName("hintLabel")
        content.addWidget(hint)
        self._trans.append(("threshold_hint", hint))
        session_hint = QLabel(tr("session_hint"))
        session_hint.setObjectName("hintLabel")
        session_hint.setWordWrap(True)
        content.addWidget(session_hint)
        self._trans.append(("session_hint", session_hint))
        self._build_focus_session_rows(content)

        # -- Section: Personalization --
        content.addWidget(self._section_label("section_personalization"))
        self._build_theme_row(content, main_theme)
        self._build_categories_row(content)
        self._build_focus_data_rows(content)

        # -- Section: Color Themes --
        content.addWidget(self._section_label("section_status_colors"))
        self._color_widgets: dict[str, list[QWidget]] = {}
        for profile_id in STATUS_DISPLAY_NAMES:
            self._build_color_row(content, profile_id)

        # -- Section: Debug --
        content.addWidget(self._section_label("Debug"))
        self._build_debug_section(content)

        scroll.setWidget(scroll_content)
        outer.addWidget(scroll, stretch=1)

        # ── Bottom action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._home_btn = QPushButton(tr("home_btn"))
        self._home_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._home_btn.clicked.connect(self.home_requested.emit)
        btn_row.addWidget(self._home_btn)
        self._trans.append(("home_btn", self._home_btn))

        btn_row.addStretch()

        self._reset_btn = QPushButton(tr("reset_btn"))
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.clicked.connect(self.reset_requested.emit)
        btn_row.addWidget(self._reset_btn)
        self._trans.append(("reset_btn", self._reset_btn))

        self._quit_btn = QPushButton(tr("quit_btn"))
        self._quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._trans.append(("quit_btn", self._quit_btn))
        self._quit_btn.clicked.connect(self.quit_requested.emit)
        btn_row.addWidget(self._quit_btn)

        outer.addLayout(btn_row)

        self._apply_theme_styles()

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _section_label(self, key: str) -> QLabel:
        lbl = QLabel(tr(key))
        lbl.setObjectName("sectionTitle")
        self._trans.append((key, lbl))
        return lbl

    def _build_dark_mode_row(self, container: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(12)

        label = QLabel(tr("dark_mode"))
        label.setObjectName("settingLabel")
        row.addWidget(label)
        self._trans.append(("dark_mode", label))

        self._dark_toggle = QPushButton("ON")
        self._dark_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dark_toggle.setFixedWidth(64)
        self._dark_toggle.clicked.connect(self._on_dark_mode_clicked)
        row.addWidget(self._dark_toggle)
        row.addStretch()

        container.addLayout(row)

    def _build_language_row(self, container: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(12)

        label = QLabel(tr("language_label"))
        label.setObjectName("settingLabel")
        row.addWidget(label)
        self._trans.append(("language_label", label))

        self._language_combo = _ClickOnlyComboBox()
        self._language_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for code, native in SUPPORTED_LANGUAGES:
            self._language_combo.addItem(native, code)
        self._language_combo.currentIndexChanged.connect(self._on_language_changed)
        row.addWidget(self._language_combo)
        row.addStretch()

        container.addLayout(row)

    def _build_slider_row(
        self,
        container: QVBoxLayout,
        label_key: str,
        initial: int,
        lo: int,
        hi: int,
        fmt: str,
    ) -> tuple[QSlider, QLabel]:
        row = QHBoxLayout()
        row.setSpacing(12)

        label = QLabel(tr(label_key))
        label.setObjectName("settingLabel")
        row.addWidget(label)
        self._trans.append((label_key, label))

        slider = _ClickOnlySlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(initial)
        slider.setMinimumWidth(180)
        row.addWidget(slider, stretch=1)

        value_label = QLabel(fmt.format(initial if fmt.endswith("%") else initial / 100))
        value_label.setObjectName("valueLabel")
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(value_label)

        def _on_change(val: int) -> None:
            value_label.setText(fmt.format(val if fmt.endswith("%") else val / 100))
            if slider is self._volume_slider:
                self.volume_changed.emit(val / 100.0)
            elif slider is self._threshold_slider:
                self.threshold_changed.emit(val / 100.0)
            elif getattr(self, "_wave_slider", None) is slider:
                self.waveform_smoothness_changed.emit(val / 100.0)
            elif getattr(self, "_aurora_slider", None) is slider:
                self.aurora_brightness_gain_changed.emit(val / 100.0)
            elif getattr(self, "_muffle_slider", None) is slider:
                self.muffling_strength_changed.emit(val / 100.0)
            elif getattr(self, "_muffle_curve_slider", None) is slider:
                self.muffling_curve_changed.emit(val / 100.0)
            elif getattr(self, "_intensity_smooth_slider", None) is slider:
                self.intensity_smoothing_changed.emit(val / 100.0)
            elif getattr(self, "_gain_slew_slider", None) is slider:
                self.gain_slew_changed.emit(val / 100.0)
            elif getattr(self, "_focus_smooth_slider", None) is slider:
                self.focus_smoothing_changed.emit(val / 100.0)
            elif getattr(self, "_scenario_xfade_slider", None) is slider:
                self.scenario_crossfade_changed.emit(val / 100.0)

        slider.valueChanged.connect(_on_change)

        container.addLayout(row)
        return slider, value_label

    def _build_debug_section(self, container: QVBoxLayout) -> None:
        self._debug_focus_enabled = False
        self._debug_layer_enabled = False
        self._debug_focus_score = 0.6
        self._debug_layer_gains = {lid: 0.7 for lid in LAYER_IDS}
        self._layer_sliders: dict[str, QSlider] = {}
        self._layer_value_labels: dict[str, QLabel] = {}

        # Manual concentration override
        focus_row = QHBoxLayout()
        focus_row.setSpacing(12)
        focus_label = QLabel("Manual Concentration")
        focus_label.setObjectName("settingLabel")
        focus_row.addWidget(focus_label)
        self._debug_focus_toggle = QPushButton("OFF")
        self._debug_focus_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._debug_focus_toggle.setFixedWidth(64)
        self._debug_focus_toggle.clicked.connect(self._on_debug_focus_toggled)
        focus_row.addWidget(self._debug_focus_toggle)
        focus_row.addStretch()
        container.addLayout(focus_row)

        self._debug_focus_slider, self._debug_focus_label = self._build_plain_slider_row(
            container,
            "Concentration Level",
            int(round(self._debug_focus_score * 100)),
            0,
            100,
            "{:d}%",
            on_change=self._on_debug_focus_slider,
        )
        self._debug_focus_slider.setEnabled(False)
        focus_hint = QLabel(
            "When ON, overrides live focus scoring so you can audition music/UI response."
        )
        focus_hint.setObjectName("hintLabel")
        focus_hint.setWordWrap(True)
        container.addWidget(focus_hint)

        # Manual layer volumes
        layer_row = QHBoxLayout()
        layer_row.setSpacing(12)
        layer_label = QLabel("Manual Layer Volumes")
        layer_label.setObjectName("settingLabel")
        layer_row.addWidget(layer_label)
        self._debug_layer_toggle = QPushButton("OFF")
        self._debug_layer_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._debug_layer_toggle.setFixedWidth(64)
        self._debug_layer_toggle.clicked.connect(self._on_debug_layer_toggled)
        layer_row.addWidget(self._debug_layer_toggle)
        layer_row.addStretch()
        container.addLayout(layer_row)

        layer_hint = QLabel(
            "When ON, bypasses focus-based mix curves and sets each stem gain directly."
        )
        layer_hint.setObjectName("hintLabel")
        layer_hint.setWordWrap(True)
        container.addWidget(layer_hint)

        self._layer_sliders_host = QWidget()
        layer_host_layout = QVBoxLayout(self._layer_sliders_host)
        layer_host_layout.setContentsMargins(0, 0, 0, 0)
        layer_host_layout.setSpacing(8)
        for layer_id in LAYER_IDS:
            title = self.LAYER_LABELS.get(layer_id, layer_id)
            slider, value_label = self._build_plain_slider_row(
                layer_host_layout,
                title,
                int(round(self._debug_layer_gains[layer_id] * 100)),
                0,
                100,
                "{:d}%",
                on_change=lambda val, lid=layer_id: self._on_debug_layer_slider(lid, val),
            )
            slider.setEnabled(False)
            self._layer_sliders[layer_id] = slider
            self._layer_value_labels[layer_id] = value_label
        self._layer_sliders_host.setVisible(False)
        container.addWidget(self._layer_sliders_host)

    def _build_plain_slider_row(
        self,
        container: QVBoxLayout,
        label_text: str,
        initial: int,
        lo: int,
        hi: int,
        fmt: str,
        *,
        on_change,
    ) -> tuple[QSlider, QLabel]:
        row = QHBoxLayout()
        row.setSpacing(12)
        label = QLabel(label_text)
        label.setObjectName("settingLabel")
        row.addWidget(label)
        slider = _ClickOnlySlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(initial)
        slider.setMinimumWidth(180)
        row.addWidget(slider, stretch=1)
        value_label = QLabel(fmt.format(initial if fmt.endswith("%") else initial / 100))
        value_label.setObjectName("valueLabel")
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(value_label)

        def _changed(val: int) -> None:
            value_label.setText(fmt.format(val if fmt.endswith("%") else val / 100))
            on_change(val)

        slider.valueChanged.connect(_changed)
        container.addLayout(row)
        return slider, value_label

    def _on_debug_focus_toggled(self) -> None:
        self._debug_focus_enabled = not self._debug_focus_enabled
        on = self._debug_focus_enabled
        self._debug_focus_toggle.setText("ON" if on else "OFF")
        self._debug_focus_toggle.setStyleSheet(TOGGLE_ON_STYLE if on else TOGGLE_OFF_STYLE)
        self._debug_focus_slider.setEnabled(on)
        self.debug_focus_override_changed.emit(on, self._debug_focus_score)

    def _on_debug_focus_slider(self, val: int) -> None:
        self._debug_focus_score = max(0.0, min(1.0, val / 100.0))
        if self._debug_focus_enabled:
            self.debug_focus_override_changed.emit(True, self._debug_focus_score)

    def _on_debug_layer_toggled(self) -> None:
        self._debug_layer_enabled = not self._debug_layer_enabled
        on = self._debug_layer_enabled
        self._debug_layer_toggle.setText("ON" if on else "OFF")
        self._debug_layer_toggle.setStyleSheet(TOGGLE_ON_STYLE if on else TOGGLE_OFF_STYLE)
        self._layer_sliders_host.setVisible(on)
        for slider in self._layer_sliders.values():
            slider.setEnabled(on)
        self.debug_layer_override_changed.emit(on)

    def _on_debug_layer_slider(self, layer_id: str, val: int) -> None:
        gain = max(0.0, min(1.0, val / 100.0))
        self._debug_layer_gains[layer_id] = gain
        if self._debug_layer_enabled:
            self.debug_layer_gain_changed.emit(layer_id, gain)

    def _build_theme_row(self, container: QVBoxLayout, current_theme: str) -> None:
        row = QHBoxLayout()
        row.setSpacing(12)

        label = QLabel(tr("theme_label"))
        label.setObjectName("settingLabel")
        row.addWidget(label)
        self._trans.append(("theme_label", label))

        self._theme_combo = _ClickOnlyComboBox()
        self._theme_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for ctx in WorkContext:
            display = i18n_theme_label(ctx.value)
            self._theme_combo.addItem(display, ctx.value)

        # Select current theme
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == current_theme:
                self._theme_combo.setCurrentIndex(i)
                break

        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        row.addWidget(self._theme_combo)
        row.addStretch()
        container.addLayout(row)

    def _build_focus_session_rows(self, container: QVBoxLayout) -> None:
        probe_row = QHBoxLayout()
        probe_row.setSpacing(8)
        self._probe_btn = QPushButton(tr("probe_btn"))
        self._probe_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._probe_btn.clicked.connect(self.probe_requested.emit)
        probe_row.addWidget(self._probe_btn)
        self._trans.append(("probe_btn", self._probe_btn))
        probe_label = QLabel(tr("probes_label"))
        probe_label.setObjectName("settingLabel")
        probe_row.addWidget(probe_label)
        self._trans.append(("probes_label", probe_label))
        self._probes_toggle = QPushButton("ON")
        self._probes_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._probes_toggle.setFixedWidth(64)
        self._probes_enabled = True
        self._probes_toggle.clicked.connect(self._on_probes_toggled)
        probe_row.addWidget(self._probes_toggle)
        probe_row.addStretch()
        container.addLayout(probe_row)
        privacy_hint = QLabel(tr("privacy_hint"))
        privacy_hint.setObjectName("hintLabel")
        privacy_hint.setWordWrap(True)
        container.addWidget(privacy_hint)
        self._trans.append(("privacy_hint", privacy_hint))

    def _build_focus_data_rows(self, container: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._export_btn = QPushButton(tr("export_btn"))
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.clicked.connect(self.export_focus_data_requested.emit)
        row.addWidget(self._export_btn)
        self._trans.append(("export_btn", self._export_btn))
        self._delete_btn = QPushButton(tr("delete_btn"))
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.clicked.connect(self.delete_focus_data_requested.emit)
        row.addWidget(self._delete_btn)
        self._trans.append(("delete_btn", self._delete_btn))
        row.addStretch()
        container.addLayout(row)

    def _on_probes_toggled(self) -> None:
        self._probes_enabled = not self._probes_enabled
        self._probes_toggle.setText("ON" if self._probes_enabled else "OFF")
        self._probes_toggle.setStyleSheet(
            TOGGLE_ON_STYLE if self._probes_enabled else TOGGLE_OFF_STYLE
        )
        self.probes_enabled_changed.emit(self._probes_enabled)

    def _build_categories_row(self, container: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(12)

        label = QLabel(tr("categories_label"))
        label.setObjectName("settingLabel")
        row.addWidget(label)
        self._trans.append(("categories_label", label))

        self._manage_btn = QPushButton(tr("manage_btn"))
        self._manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._manage_btn.setToolTip(tr("manage_tip"))
        self._manage_btn.clicked.connect(self.categories_requested.emit)
        row.addWidget(self._manage_btn)
        self._trans.append(("manage_btn", self._manage_btn))
        row.addStretch()
        container.addLayout(row)

        hint = QLabel(tr("categories_hint"))
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        container.addWidget(hint)
        self._trans.append(("categories_hint", hint))

    def _build_color_row(self, container: QVBoxLayout, profile_id: str) -> None:
        """One row: icon + name | colour swatch | Pick button."""
        row = QHBoxLayout()
        row.setSpacing(8)

        icon_label = QLabel()
        icon_label.setFixedSize(22, 22)
        icon_label.setPixmap(
            self._color_icons["dark" if self._dark else "light"][profile_id].pixmap(22, 22)
        )
        row.addWidget(icon_label)
        self._color_icon_labels[profile_id] = icon_label

        name = i18n_status_label(profile_id)
        label = QLabel(name)
        label.setObjectName("settingLabel")
        row.addWidget(label)
        self._color_labels[profile_id] = label

        color = self._status_colors[profile_id]
        swatch = QPushButton()
        swatch.setFixedSize(28, 28)
        swatch.setEnabled(False)
        swatch.setStyleSheet(
            f"background-color:{color};border:1px solid #555;border-radius:6px;"
        )
        row.addWidget(swatch)

        pick_btn = QPushButton(tr("pick_btn"))
        pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pick_btn.clicked.connect(lambda _c, pid=profile_id, s=swatch: self._pick_color(pid, s))
        row.addWidget(pick_btn)
        self._trans.append(("pick_btn", pick_btn))

        row.addStretch()
        container.addLayout(row)

        self._color_widgets[profile_id] = [swatch, pick_btn]

    def _pick_color(self, profile_id: str, swatch: QPushButton) -> None:
        """Open QColorDialog and update the per-status colour."""
        current = QColor(self._status_colors[profile_id])
        name = i18n_status_label(profile_id)
        color = QColorDialog.getColor(current, self, tr("pick_color_for").format(name))
        if not color.isValid():
            return
        hex_color = color.name()
        self._status_colors[profile_id] = hex_color
        swatch.setStyleSheet(
            f"background-color:{hex_color};border:1px solid #555;border-radius:6px;"
        )
        self.status_colors_changed.emit(dict(self._status_colors))

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_dark_mode_clicked(self) -> None:
        self._dark = not self._dark
        self._dark_toggle.setText("ON" if self._dark else "OFF")
        self._dark_toggle.setStyleSheet(TOGGLE_ON_STYLE if self._dark else TOGGLE_OFF_STYLE)
        self.dark_mode_toggled.emit(self._dark)

    def _on_theme_changed(self, _index: int) -> None:
        data = self._theme_combo.currentData()
        if isinstance(data, str):
            self.main_theme_changed.emit(data)

    def _on_language_changed(self, _index: int) -> None:
        code = self._language_combo.currentData()
        if isinstance(code, str):
            i18n_set_language(code)
            self.retranslate()
            self.language_changed.emit(code)

    # ------------------------------------------------------------------
    # Theme switching
    # ------------------------------------------------------------------

    def set_dark_mode(self, enabled: bool) -> None:
        """Apply dark / light stylesheet."""
        self._dark = enabled
        self._apply_theme_styles()
        # Keep toggle in sync (called from MainWindow)
        self._dark_toggle.blockSignals(True)
        self._dark_toggle.setText("ON" if enabled else "OFF")
        self._dark_toggle.setStyleSheet(TOGGLE_ON_STYLE if enabled else TOGGLE_OFF_STYLE)
        self._dark_toggle.blockSignals(False)

    def _apply_theme_styles(self) -> None:
        dark = self._dark
        self.setStyleSheet(SETTINGS_STYLE if dark else LIGHT_SETTINGS_STYLE)
        self._title.setStyleSheet(TITLE_STYLE if dark else LIGHT_TITLE_STYLE)
        self._dark_toggle.setStyleSheet(TOGGLE_ON_STYLE if dark else TOGGLE_OFF_STYLE)
        self._home_btn.setStyleSheet(ACTION_BTN_STYLE if dark else ACTION_BTN_LIGHT_STYLE)
        self._reset_btn.setStyleSheet(ACTION_BTN_STYLE if dark else ACTION_BTN_LIGHT_STYLE)
        self._quit_btn.setStyleSheet(QUIT_BTN_STYLE if dark else QUIT_BTN_LIGHT_STYLE)
        btn_style = ACTION_BTN_STYLE if dark else ACTION_BTN_LIGHT_STYLE
        probe_btn = getattr(self, "_probe_btn", None)
        if probe_btn is not None:
            probe_btn.setStyleSheet(btn_style)
        if getattr(self, "_probes_toggle", None) is not None:
            self._probes_toggle.setStyleSheet(
                TOGGLE_ON_STYLE if self._probes_enabled else TOGGLE_OFF_STYLE
            )
        for toggle_attr, enabled_attr in (
            ("_debug_focus_toggle", "_debug_focus_enabled"),
            ("_debug_layer_toggle", "_debug_layer_enabled"),
        ):
            toggle = getattr(self, toggle_attr, None)
            if toggle is not None:
                enabled = bool(getattr(self, enabled_attr, False))
                toggle.setStyleSheet(TOGGLE_ON_STYLE if enabled else TOGGLE_OFF_STYLE)
        # Colour-picker buttons follow theme
        for _swatch, pick_btn in self._color_widgets.values():
            pick_btn.setStyleSheet(COLOR_PICKER_BTN_STYLE if dark else LIGHT_COLOR_PICKER_BTN_STYLE)
        self._apply_color_icons()
        # Manage / Export / Delete data buttons follow theme (white text in dark mode)
        for b in (
            getattr(self, "_manage_btn", None),
            getattr(self, "_export_btn", None),
            getattr(self, "_delete_btn", None),
        ):
            if b is not None:
                b.setStyleSheet(ACTION_BTN_WHITE_STYLE if dark else ACTION_BTN_LIGHT_STYLE)

    def _apply_color_icons(self) -> None:
        """Re-render the per-status icons for the active theme."""
        icons = self._color_icons["dark" if self._dark else "light"]
        for profile_id, icon_label in self._color_icon_labels.items():
            icon_label.setPixmap(icons[profile_id].pixmap(22, 22))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_volume(self, value: float) -> None:
        """Set master volume slider (0.0–1.0) without emitting signal."""
        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(int(round(value * 100)))
        self._volume_slider.blockSignals(False)
        self._volume_label.setText(f"{int(round(value * 100))}%")

    def set_muffling_strength(self, value: float) -> None:
        pct = int(round(max(0.0, min(1.0, value)) * 100))
        self._muffle_slider.blockSignals(True)
        self._muffle_slider.setValue(pct)
        self._muffle_slider.blockSignals(False)
        self._muffle_label.setText(f"{pct}%")

    def set_muffling_curve(self, value: float) -> None:
        scaled = int(round(max(1.0, min(5.0, value)) * 100))
        self._muffle_curve_slider.blockSignals(True)
        self._muffle_curve_slider.setValue(scaled)
        self._muffle_curve_slider.blockSignals(False)
        self._muffle_curve_label.setText(f"{scaled / 100:.1f}×")

    def set_intensity_smoothing(self, value: float) -> None:
        scaled = int(round(max(0.05, min(0.90, value)) * 100))
        self._intensity_smooth_slider.blockSignals(True)
        self._intensity_smooth_slider.setValue(scaled)
        self._intensity_smooth_slider.blockSignals(False)
        self._intensity_smooth_label.setText(f"{scaled / 100:.2f}")

    def set_gain_slew(self, value: float) -> None:
        scaled = int(round(max(0.2, min(3.0, value)) * 100))
        self._gain_slew_slider.blockSignals(True)
        self._gain_slew_slider.setValue(scaled)
        self._gain_slew_slider.blockSignals(False)
        self._gain_slew_label.setText(f"{scaled / 100:.1f}s")

    def set_focus_smoothing(self, value: float) -> None:
        scaled = int(round(max(0.05, min(0.90, value)) * 100))
        self._focus_smooth_slider.blockSignals(True)
        self._focus_smooth_slider.setValue(scaled)
        self._focus_smooth_slider.blockSignals(False)
        self._focus_smooth_label.setText(f"{scaled / 100:.2f}")

    def set_scenario_crossfade(self, value: float) -> None:
        scaled = int(round(max(0.5, min(12.0, value)) * 100))
        self._scenario_xfade_slider.blockSignals(True)
        self._scenario_xfade_slider.setValue(scaled)
        self._scenario_xfade_slider.blockSignals(False)
        self._scenario_xfade_label.setText(f"{scaled / 100:.1f}s")

    def set_probes_enabled(self, enabled: bool) -> None:
        self._probes_enabled = bool(enabled)
        self._probes_toggle.setText("ON" if self._probes_enabled else "OFF")
        self._probes_toggle.setStyleSheet(
            TOGGLE_ON_STYLE if self._probes_enabled else TOGGLE_OFF_STYLE
        )

    def set_threshold(self, value: float) -> None:
        """Set concentration threshold (0.2–2.0) without emitting signal."""
        self._threshold_slider.blockSignals(True)
        self._threshold_slider.setValue(int(round(value * 100)))
        self._threshold_slider.blockSignals(False)
        self._threshold_label.setText(f"{value:.1f}")

    def set_waveform_smoothness(self, value: float) -> None:
        """Set waveform smoothness slider (0.0–1.0) without emitting signal."""
        pct = int(round(max(0.0, min(1.0, value)) * 100))
        self._wave_slider.blockSignals(True)
        self._wave_slider.setValue(pct)
        self._wave_slider.blockSignals(False)
        self._wave_label.setText(f"{pct}%")

    def set_aurora_brightness_gain(self, value: float) -> None:
        """Set aurora brightness gain slider (0.0–3.0) without emitting signal."""
        scaled = int(round(max(0.0, min(3.0, value)) * 100))
        self._aurora_slider.blockSignals(True)
        self._aurora_slider.setValue(scaled)
        self._aurora_slider.blockSignals(False)
        self._aurora_label.setText(f"{scaled / 100:.1f}×")

    def set_main_theme(self, theme: str) -> None:
        """Select main theme combo without emitting signal."""
        self._theme_combo.blockSignals(True)
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == theme:
                self._theme_combo.setCurrentIndex(i)
                break
        self._theme_combo.blockSignals(False)

    def set_language(self, code: str) -> None:
        """Switch UI language without re-emitting the language_changed signal."""
        i18n_set_language(code)
        self._language_combo.blockSignals(True)
        for i in range(self._language_combo.count()):
            if self._language_combo.itemData(i) == code:
                self._language_combo.setCurrentIndex(i)
                break
        self._language_combo.blockSignals(False)
        self.retranslate()

    def retranslate(self) -> None:
        """Re-apply the active language to every static string on the page."""
        for key, widget in self._trans:
            widget.setText(tr(key))
        for profile_id, label in self._color_labels.items():
            label.setText(i18n_status_label(profile_id))
        if getattr(self, "_manage_btn", None) is not None:
            self._manage_btn.setToolTip(tr("manage_tip"))
        # Rebuild theme combo items (localized) while keeping the selection
        combo = getattr(self, "_theme_combo", None)
        if combo is not None:
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for ctx in WorkContext:
                combo.addItem(i18n_theme_label(ctx.value), ctx.value)
            for i in range(combo.count()):
                if combo.itemData(i) == current:
                    combo.setCurrentIndex(i)
                    break
            combo.blockSignals(False)

    def get_status_colors(self) -> dict[str, str]:
        """Return the current per-status colour map (profile_id → hex)."""
        return dict(self._status_colors)

    def set_status_colors(self, colors: dict[str, str]) -> None:
        """Restore per-status colours from an external dict."""
        self._status_colors.update(colors)
        for profile_id, (swatch, _pick_btn) in self._color_widgets.items():
            if profile_id in self._status_colors:
                c = self._status_colors[profile_id]
                swatch.setStyleSheet(
                    f"background-color:{c};border:1px solid #555;border-radius:6px;"
                )

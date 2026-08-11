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
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from adaptive_soundscape.core.events import WorkContext

# ---------------------------------------------------------------------------
# Theme labels (shared with home_page)
# ---------------------------------------------------------------------------
THEME_LABELS: dict[WorkContext, str] = {
    WorkContext.PROGRAMMING: "Coding",
    WorkContext.TEAM_WORKFLOW: "Collaborating",
    WorkContext.READING_WRITING: "Reading & Writing",
    WorkContext.SCIENTIFIC: "Research",
    WorkContext.CREATIVE_DESIGN: "Creating",
    WorkContext.DISTRACTION: "Distracted",
    WorkContext.UNKNOWN: "Neutral",
}

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

STATUS_ICONS: dict[str, str] = {
    "programming":     "🖥️",
    "team_workflow":   "👥",
    "reading_writing": "📖",
    "scientific":      "🔬",
    "creative_design": "🎨",
    "distraction":     "⚠️",
    "unknown":         "◯",
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
    main_theme_changed = pyqtSignal(str)
    quit_requested = pyqtSignal()
    reset_requested = pyqtSignal()
    home_requested = pyqtSignal()
    categories_requested = pyqtSignal()
    status_colors_changed = pyqtSignal(dict)

    DEFAULT_WAVEFORM_SMOOTHNESS = 0.35

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        master_volume: float = 0.75,
        sensitivity: float = 1.0,
        main_theme: str = "unknown",
        waveform_smoothness: float = DEFAULT_WAVEFORM_SMOOTHNESS,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self._dark = True
        self._status_colors: dict[str, str] = dict(DEFAULT_STATUS_COLORS)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 28, 40, 24)
        outer.setSpacing(0)

        # ── Title ──
        self._title = QLabel("Settings")
        self._title.setObjectName("pageTitle")
        outer.addWidget(self._title)

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

        # -- Section: Appearance --
        content.addWidget(self._section_label("Appearance"))
        self._build_dark_mode_row(content)
        self._wave_slider, self._wave_label = self._build_slider_row(
            content,
            "Waveform Smoothness",
            int(round(waveform_smoothness * 100)),
            0,
            100,
            "{:d}%",
        )
        wave_hint = QLabel("Lower  →  more detailed ring ·  Higher  →  softer oval glow")
        wave_hint.setObjectName("hintLabel")
        content.addWidget(wave_hint)

        # -- Section: Audio --
        content.addWidget(self._section_label("Audio"))
        self._volume_slider, self._volume_label = self._build_slider_row(
            content, "Master Volume", int(master_volume * 100), 0, 100, "{:d}%"
        )

        # -- Section: Cognitive --
        content.addWidget(self._section_label("Cognitive"))
        self._threshold_slider, self._threshold_label = self._build_slider_row(
            content,
            "Concentration Threshold",
            int(sensitivity * 100),
            20,
            200,
            "{:.1f}",
        )
        hint = QLabel("Higher  →  more easily detected as distracted")
        hint.setObjectName("hintLabel")
        content.addWidget(hint)

        # -- Section: Personalization --
        content.addWidget(self._section_label("Personalization"))
        self._build_theme_row(content, main_theme)
        self._build_categories_row(content)

        # -- Section: Color Themes --
        content.addWidget(self._section_label("Status Colors"))
        self._color_widgets: dict[str, list[QWidget]] = {}
        for profile_id in STATUS_DISPLAY_NAMES:
            self._build_color_row(content, profile_id)

        scroll.setWidget(scroll_content)
        outer.addWidget(scroll, stretch=1)

        # ── Bottom action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._home_btn = QPushButton("Return to Home")
        self._home_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._home_btn.clicked.connect(self.home_requested.emit)
        btn_row.addWidget(self._home_btn)

        btn_row.addStretch()

        self._reset_btn = QPushButton("Reset Settings")
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.clicked.connect(self.reset_requested.emit)
        btn_row.addWidget(self._reset_btn)

        self._quit_btn = QPushButton("Quit App")
        self._quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._quit_btn.clicked.connect(self.quit_requested.emit)
        btn_row.addWidget(self._quit_btn)

        outer.addLayout(btn_row)

        self._apply_theme_styles()

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    def _build_dark_mode_row(self, container: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(12)

        label = QLabel("Dark Mode")
        label.setObjectName("settingLabel")
        row.addWidget(label)

        self._dark_toggle = QPushButton("ON")
        self._dark_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dark_toggle.setFixedWidth(64)
        self._dark_toggle.clicked.connect(self._on_dark_mode_clicked)
        row.addWidget(self._dark_toggle)
        row.addStretch()

        container.addLayout(row)

    def _build_slider_row(
        self,
        container: QVBoxLayout,
        label_text: str,
        initial: int,
        lo: int,
        hi: int,
        fmt: str,
    ) -> tuple[QSlider, QLabel]:
        row = QHBoxLayout()
        row.setSpacing(12)

        label = QLabel(label_text)
        label.setObjectName("settingLabel")
        row.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
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

        slider.valueChanged.connect(_on_change)

        container.addLayout(row)
        return slider, value_label

    def _build_theme_row(self, container: QVBoxLayout, current_theme: str) -> None:
        row = QHBoxLayout()
        row.setSpacing(12)

        label = QLabel("Main Theme")
        label.setObjectName("settingLabel")
        row.addWidget(label)

        self._theme_combo = QComboBox()
        self._theme_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for ctx in WorkContext:
            display = THEME_LABELS.get(ctx, ctx.value.title())
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

    def _build_categories_row(self, container: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(12)

        label = QLabel("Window Categories")
        label.setObjectName("settingLabel")
        row.addWidget(label)

        btn = QPushButton("Manage…")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(
            "Edit saved process names and title keywords used for window classification."
        )
        btn.clicked.connect(self.categories_requested.emit)
        row.addWidget(btn)
        row.addStretch()
        container.addLayout(row)

        hint = QLabel(
            "Choices from the unknown-window toast are saved here and kept after restart."
        )
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        container.addWidget(hint)

    def _build_color_row(self, container: QVBoxLayout, profile_id: str) -> None:
        """One row: icon + name | colour swatch | Pick button."""
        row = QHBoxLayout()
        row.setSpacing(8)

        icon = STATUS_ICONS.get(profile_id, "⚫")
        name = STATUS_DISPLAY_NAMES.get(profile_id, profile_id)
        label = QLabel(f"{icon}  {name}")
        label.setObjectName("settingLabel")
        row.addWidget(label)

        color = self._status_colors[profile_id]
        swatch = QPushButton()
        swatch.setFixedSize(28, 28)
        swatch.setEnabled(False)
        swatch.setStyleSheet(
            f"background-color:{color};border:1px solid #555;border-radius:6px;"
        )
        row.addWidget(swatch)

        pick_btn = QPushButton("Pick\u2026")
        pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pick_btn.clicked.connect(lambda _c, pid=profile_id, s=swatch: self._pick_color(pid, s))
        row.addWidget(pick_btn)

        row.addStretch()
        container.addLayout(row)

        self._color_widgets[profile_id] = [swatch, pick_btn]

    def _pick_color(self, profile_id: str, swatch: QPushButton) -> None:
        """Open QColorDialog and update the per-status colour."""
        current = QColor(self._status_colors[profile_id])
        color = QColorDialog.getColor(current, self, f"Pick colour for {STATUS_DISPLAY_NAMES.get(profile_id, profile_id)}")
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
        # Colour-picker buttons follow theme
        for _swatch, pick_btn in self._color_widgets.values():
            pick_btn.setStyleSheet(COLOR_PICKER_BTN_STYLE if dark else LIGHT_COLOR_PICKER_BTN_STYLE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_volume(self, value: float) -> None:
        """Set master volume slider (0.0–1.0) without emitting signal."""
        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(int(round(value * 100)))
        self._volume_slider.blockSignals(False)
        self._volume_label.setText(f"{int(round(value * 100))}%")

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

    def set_main_theme(self, theme: str) -> None:
        """Select main theme combo without emitting signal."""
        self._theme_combo.blockSignals(True)
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == theme:
                self._theme_combo.setCurrentIndex(i)
                break
        self._theme_combo.blockSignals(False)

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

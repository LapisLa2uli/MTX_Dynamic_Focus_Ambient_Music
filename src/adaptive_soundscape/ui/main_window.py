"""Main application window with sidebar navigation and page stack."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from adaptive_soundscape.core.events import FocusState, WorkContext
from adaptive_soundscape.core.i18n import (
    set_language as i18n_set_language,
    tr,
)
from adaptive_soundscape.ui.home_page import HomePage
from adaptive_soundscape.ui.inference_toast import InferenceToast
from adaptive_soundscape.ui.settings_page import SettingsPage
from adaptive_soundscape.ui.upload_page import UploadPage

SIDEBAR_WIDTH = 190

DARK_STYLE = """
QMainWindow {
    background-color: #1a1a1e;
    color: #e8e8ec;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QPushButton {
    background-color: #33333a;
    border: 1px solid #44444d;
    border-radius: 6px;
    padding: 8px 14px;
}
QPushButton:hover { background-color: #3d3d46; }
QComboBox, QDoubleSpinBox {
    background-color: #25252b;
    border: 1px solid #44444d;
    border-radius: 4px;
    padding: 4px 8px;
}
QCheckBox { spacing: 8px; }
"""

LIGHT_STYLE = """
QMainWindow {
    background-color: #f5f5f8;
    color: #1a1a1e;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QPushButton {
    background-color: #e0e0e5;
    border: 1px solid #c0c0c8;
    border-radius: 6px;
    padding: 8px 14px;
    color: #1a1a1e;
}
QPushButton:hover { background-color: #d0d0d8; }
QComboBox, QDoubleSpinBox {
    background-color: #ffffff;
    border: 1px solid #c0c0c8;
    border-radius: 4px;
    padding: 4px 8px;
}
QCheckBox { spacing: 8px; }
"""

SIDEBAR_STYLE = """
QWidget#sidebar {
    background-color: #16161a;
    border-right: 1px solid #2a2a30;
}
"""

LIGHT_SIDEBAR_STYLE = """
QWidget#sidebar {
    background-color: #ededf2;
    border-right: 1px solid #d0d0d8;
}
"""

NAV_BTN_BASE = """
QPushButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #88889a;
    font-size: 16px;
    font-weight: 700;
    text-align: left;
    padding: 16px 20px;
}
QPushButton:hover {
    background-color: #22222a;
    color: #c0c0d0;
}
"""

NAV_BTN_ACTIVE = """
QPushButton {
    background-color: #242430;
    border-left: 3px solid #5b8def;
    border-radius: 0 8px 8px 0;
    color: #e8e8ec;
    font-size: 16px;
    font-weight: 700;
    text-align: left;
    padding: 16px 20px;
}
"""

LIGHT_NAV_BTN_BASE = """
QPushButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #707080;
    font-size: 16px;
    font-weight: 700;
    text-align: left;
    padding: 16px 20px;
}
QPushButton:hover {
    background-color: #e0e0e8;
    color: #383848;
}
"""

LIGHT_NAV_BTN_ACTIVE = """
QPushButton {
    background-color: #e0e0e8;
    border-left: 3px solid #5b8def;
    border-radius: 0 8px 8px 0;
    color: #181820;
    font-size: 16px;
    font-weight: 700;
    text-align: left;
    padding: 16px 20px;
}
"""


NAV_ITEMS = [
    ("nav_home", 0),
    ("nav_upload", 1),
    ("nav_settings", 2),
]


class MainWindow(QMainWindow):
    """Dark dashboard with sidebar navigation.

    ┌──────────┬──────────────────────────┐
    │ Sidebar  │   QStackedWidget         │
    │          │                          │
    │ • Home   │   Home / Upload /        │
    │ • Upload │   Settings page          │
    │ • Sett.  │                          │
    └──────────┴──────────────────────────┘
    """

    categories_clicked = pyqtSignal()
    albums_clicked = pyqtSignal()
    classify_requested = pyqtSignal()  # user clicked "Confirm Classification"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(tr("window_title"))
        self.setMinimumSize(780, 540)
        self._dark = True
        self._current_nav_index = 0
        from adaptive_soundscape.ui.settings_page import DEFAULT_STATUS_COLORS

        self._status_colors = dict(DEFAULT_STATUS_COLORS)
        self._status_tint: str | None = None
        self._applying_tint = False
        self.setStyleSheet(DARK_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ──
        self._sidebar = QWidget()
        self._sidebar.setObjectName("sidebar")
        self._sidebar.setFixedWidth(SIDEBAR_WIDTH)
        self._sidebar.setStyleSheet(SIDEBAR_STYLE)
        sidebar_layout = QVBoxLayout(self._sidebar)
        sidebar_layout.setContentsMargins(8, 24, 8, 16)
        sidebar_layout.setSpacing(4)

        self._nav_buttons: list[QPushButton] = []
        for key, idx in NAV_ITEMS:
            btn = QPushButton(tr(key))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked, i=idx: self._navigate(i))
            sidebar_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        sidebar_layout.addStretch()

        root.addWidget(self._sidebar)

        # ── Content area (host for pages + in-window confirmation overlay) ──
        self._content_host = QWidget()
        self._content_host.setObjectName("contentHost")
        right = QVBoxLayout(self._content_host)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        self._pages = QStackedWidget()

        self._home_page = HomePage()
        self._upload_page = UploadPage()
        self._settings_page = SettingsPage()

        self._pages.addWidget(self._home_page)    # index 0
        self._pages.addWidget(self._upload_page)   # index 1
        self._pages.addWidget(self._settings_page)  # index 2

        right.addWidget(self._pages, stretch=1)

        # ── Status label ──
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            "color: #c07070; font-size: 11px; font-weight: 700;"
            "padding: 4px 20px 8px 20px;"
        )
        self._status_label.setWordWrap(True)
        right.addWidget(self._status_label)

        root.addWidget(self._content_host, stretch=1)

        # Classification confirmations appear inside the main window (not a popup).
        self.inference_toast = InferenceToast(self._content_host)

        # ── Hidden legacy controls (app.py backward-compat) ──
        self._build_hidden_controls()

        # ── Wire settings signals ──
        self._settings_page.home_requested.connect(lambda: self._navigate(0))
        self._settings_page.dark_mode_toggled.connect(self._set_dark_mode)
        self._settings_page.status_colors_changed.connect(self._on_status_colors)

        # Start on Home
        self._current_nav_index = 0
        self._navigate(0)

    # ------------------------------------------------------------------
    # Hidden controls
    # ------------------------------------------------------------------
    def _build_hidden_controls(self) -> None:
        self._override_check = QCheckBox("Manual override")
        self._override_check.setVisible(False)
        self._context_combo = QComboBox()
        self._context_combo.setVisible(False)
        for ctx in WorkContext:
            if ctx != WorkContext.UNKNOWN:
                self._context_combo.addItem(ctx.value.replace("_", " ").title(), ctx)
        self._sensitivity_spin = QDoubleSpinBox()
        self._sensitivity_spin.setVisible(False)
        self._sensitivity_spin.setRange(0.2, 2.0)
        self._sensitivity_spin.setSingleStep(0.1)
        self._sensitivity_spin.setValue(1.0)
        self._title_check = QCheckBox("Collect window titles")
        self._title_check.setVisible(False)
        self._title_check.setChecked(True)
        self._process_check = QCheckBox("Collect process names")
        self._process_check.setVisible(False)
        self._process_check.setChecked(True)
        self._log_check = QCheckBox("Activity logging")
        self._log_check.setVisible(False)
        self._log_check.setChecked(False)

        # Dummy buttons — keep old attribute names alive for safety.
        self._audio_btn = QPushButton()
        self._audio_btn.setVisible(False)
        self._categories_btn = QPushButton()
        self._categories_btn.setVisible(False)
        self._albums_btn = QPushButton()
        self._albums_btn.setVisible(False)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _navigate(self, index: int) -> None:
        self._current_nav_index = index
        self._pages.setCurrentIndex(index)
        active_style = NAV_BTN_ACTIVE if self._dark else LIGHT_NAV_BTN_ACTIVE
        base_style = NAV_BTN_BASE if self._dark else LIGHT_NAV_BTN_BASE
        for i, btn in enumerate(self._nav_buttons):
            btn.setStyleSheet(active_style if i == index else base_style)

    # ------------------------------------------------------------------
    # Theme switching
    # ------------------------------------------------------------------

    def _set_dark_mode(self, enabled: bool) -> None:
        """Toggle between dark and light application theme."""
        self._dark = enabled
        self.setStyleSheet(DARK_STYLE if enabled else LIGHT_STYLE)
        self._sidebar.setStyleSheet(SIDEBAR_STYLE if enabled else LIGHT_SIDEBAR_STYLE)

        # Re-apply nav button styles for current active index
        active_style = NAV_BTN_ACTIVE if enabled else LIGHT_NAV_BTN_ACTIVE
        base_style = NAV_BTN_BASE if enabled else LIGHT_NAV_BTN_BASE
        for i, btn in enumerate(self._nav_buttons):
            btn.setStyleSheet(active_style if i == self._current_nav_index else base_style)

        # Push theme to child pages
        self._home_page.set_dark_mode(enabled)
        self._upload_page.set_dark_mode(enabled)
        self._settings_page.set_dark_mode(enabled)
        self.inference_toast.set_dark_mode(enabled)

        # Reapply current status tint after theme switch
        self._apply_page_tint()

    @property
    def is_dark_mode(self) -> bool:
        return self._dark

    def _on_status_colors(self, colors: dict[str, str]) -> None:
        """Store the latest per-status colour map (Home aurora follows context)."""
        self._status_colors.update(colors)

    def _apply_page_tint(self) -> None:
        """Re-apply the stored status tint on Upload/Settings (Home uses aurora)."""
        if self._status_tint is None:
            return
        self._applying_tint = True
        for page in (self._upload_page, self._settings_page):
            style = page.styleSheet() or ""
            style = style.rstrip()
            # Remove any previously appended background-color override
            if "\nbackground-color:" in style:
                style = style[: style.rindex("\nbackground-color:")]
            page.setStyleSheet(f"{style}\nbackground-color: {self._status_tint};")
        self._applying_tint = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_status_background(self, profile_id: str) -> None:
        """Tint Upload/Settings and drive Home aurora from the status colour."""
        from adaptive_soundscape.ui.settings_page import DEFAULT_STATUS_COLORS

        hex_color = self._status_colors.get(profile_id) or DEFAULT_STATUS_COLORS.get(
            profile_id, DEFAULT_STATUS_COLORS["unknown"]
        )
        self._home_page.set_aurora_color(hex_color)
        if self._dark:
            base_r, base_g, base_b = 26, 26, 32
        else:
            base_r, base_g, base_b = 245, 245, 248
        c = QColor(hex_color)
        r = int(base_r * 0.88 + c.red() * 0.12)
        g = int(base_g * 0.88 + c.green() * 0.12)
        b = int(base_b * 0.88 + c.blue() * 0.12)
        self._status_tint = QColor(r, g, b).name()
        self._apply_page_tint()

    @property
    def home_page(self) -> HomePage:
        return self._home_page

    @property
    def upload_page(self) -> UploadPage:
        return self._upload_page

    @property
    def settings_page(self) -> SettingsPage:
        return self._settings_page

    def set_status_message(self, message: str) -> None:
        self._status_label.setText(message)

    def set_language(self, code: str) -> None:
        """Switch UI language across the whole window."""
        i18n_set_language(code)
        self.setWindowTitle(tr("window_title"))
        for btn, (key, _idx) in zip(self._nav_buttons, NAV_ITEMS):
            btn.setText(tr(key))
        self._home_page.set_language(code)
        self._upload_page.set_language(code)
        self._settings_page.set_language(code)

    def update_status(
        self,
        *,
        context: WorkContext,
        focus_state: FocusState,
        focus_score: float,
        profile_name: str,
        music_state: str = "",
        music_detail: str = "",
    ) -> None:
        del focus_state, profile_name
        from adaptive_soundscape.ui.settings_page import DEFAULT_STATUS_COLORS

        theme_color = self._status_colors.get(context.value) or DEFAULT_STATUS_COLORS.get(
            context.value, DEFAULT_STATUS_COLORS["unknown"]
        )
        self._home_page.update_status(
            context=context,
            focus_score=focus_score,
            music_state=music_state,
            music_detail=music_detail,
            theme_color=theme_color,
        )

    @property
    def manual_override_enabled(self) -> bool:
        return self._override_check.isChecked()

    @property
    def manual_context(self) -> WorkContext:
        data = self._context_combo.currentData()
        return data if isinstance(data, WorkContext) else WorkContext.UNKNOWN

    @property
    def sensitivity(self) -> float:
        return self._sensitivity_spin.value()

    def privacy_settings(self) -> tuple[bool, bool, bool]:
        return (
            self._title_check.isChecked(),
            self._process_check.isChecked(),
            self._log_check.isChecked(),
        )

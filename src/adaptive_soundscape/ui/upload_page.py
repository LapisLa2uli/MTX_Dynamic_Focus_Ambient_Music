"""Upload page — per-status soundtrack management with drag-drop and SWAP."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from adaptive_soundscape.audio.album import (
    PROFILE_IDS,
    add_track,
    display_name_for_profile,
    list_tracks,
)
from adaptive_soundscape.audio.loader import SUPPORTED_EXTENSIONS

# Profile → icon mapping for tab buttons
PROFILE_ICONS: dict[str, str] = {
    "programming": "🖥️",
    "team_workflow": "👥",
    "reading_writing": "📖",
    "scientific": "🔬",
    "creative_design": "🎨",
    "distraction": "⚠️",
    "unknown": "◯",
}

UPLOAD_STYLE = """
QWidget#uploadPage {
    background-color: #1a1a1e;
}
QLabel#pageTitle {
    color: #e8e8ec;
    font-size: 20px;
    font-weight: 800;
}
QLabel#subtitleLabel {
    color: #c0c0d0;
    font-size: 16px;
    font-weight: 700;
}
QLabel#currentTrackLabel {
    color: #5b8def;
    font-size: 12px;
    font-weight: 700;
}
QLabel#noTrackLabel {
    color: #7a7a8a;
    font-size: 12px;
    font-weight: 700;
}
QLabel#tabSubtitle {
    color: #a0a0b8;
    font-size: 14px;
    font-weight: 600;
    padding-left: 2px;
}
"""

LIGHT_UPLOAD_STYLE = """
QWidget#uploadPage {
    background-color: #f5f5f8;
}
QLabel#pageTitle {
    color: #1a1a1e;
    font-size: 20px;
    font-weight: 800;
}
QLabel#subtitleLabel {
    color: #3a3a48;
    font-size: 16px;
    font-weight: 700;
}
QLabel#currentTrackLabel {
    color: #3d6fd4;
    font-size: 12px;
    font-weight: 700;
}
QLabel#noTrackLabel {
    color: #808090;
    font-size: 12px;
    font-weight: 700;
}
QLabel#tabSubtitle {
    color: #505068;
    font-size: 14px;
    font-weight: 600;
    padding-left: 2px;
}
"""

TAB_BASE = """
QPushButton {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: #70707a;
    font-size: 12px;
    font-weight: 700;
    padding: 6px 14px;
}
QPushButton:hover {
    color: #a0a0b0;
}
"""

TAB_ACTIVE = """
QPushButton {
    background: transparent;
    border: none;
    border-bottom: 2px solid #5b8def;
    color: #e8e8ec;
    font-size: 12px;
    font-weight: 700;
    padding: 6px 14px;
}
"""

LIGHT_TAB_BASE = """
QPushButton {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: #808090;
    font-size: 12px;
    font-weight: 700;
    padding: 6px 14px;
}
QPushButton:hover {
    color: #404050;
}
"""

LIGHT_TAB_ACTIVE = """
QPushButton {
    background: transparent;
    border: none;
    border-bottom: 2px solid #5b8def;
    color: #181820;
    font-size: 12px;
    font-weight: 700;
    padding: 6px 14px;
}
"""

TRACK_BAR_STYLE = """
QFrame#trackBar {
    background-color: #272730;
    border: 1px solid #3e3e50;
    border-radius: 6px;
    padding: 8px 12px;
}
"""

LIGHT_TRACK_BAR_STYLE = """
QFrame#trackBar {
    background-color: #e8e8ee;
    border: 1px solid #c0c0c8;
    border-radius: 6px;
    padding: 8px 12px;
}
"""

UPLOAD_ZONE_STYLE = """
QFrame#uploadZone {
    background-color: #262632;
    border: 3px dashed #7a7a90;
    border-radius: 10px;
}
QFrame#uploadZone:hover {
    border-color: #5b8def;
    background-color: #2c2c38;
}
QLabel#uploadIcon {
    color: #b8b8c8;
    font-size: 40px;
    font-weight: 700;
}
QLabel#uploadHint {
    color: #d0d0e0;
    font-size: 14px;
    font-weight: 700;
}
QLabel#uploadedName {
    color: #5b8def;
    font-size: 14px;
    font-weight: 700;
}
"""

LIGHT_UPLOAD_ZONE_STYLE = """
QFrame#uploadZone {
    background-color: #eeeef2;
    border: 3px dashed #a0a0b8;
    border-radius: 10px;
}
QFrame#uploadZone:hover {
    border-color: #5b8def;
    background-color: #e4e4ec;
}
QLabel#uploadIcon {
    color: #5a5a70;
    font-size: 40px;
    font-weight: 700;
}
QLabel#uploadHint {
    color: #4a4a58;
    font-size: 14px;
    font-weight: 700;
}
QLabel#uploadedName {
    color: #3d6fd4;
    font-size: 14px;
    font-weight: 700;
}
"""

SWAP_ENABLED = """
QPushButton {
    background-color: #5b8def;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 800;
    padding: 10px 28px;
}
QPushButton:hover { background-color: #6b9dff; }
QPushButton:pressed { background-color: #4a7dde; }
"""

SWAP_DISABLED = """
QPushButton {
    background-color: #2a2a34;
    color: #505060;
    border: 1px solid #333340;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 800;
    padding: 10px 28px;
}
"""


class _UploadZone(QFrame):
    """Clickable / droppable file staging area."""

    file_staged = pyqtSignal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("uploadZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(200)
        self.setStyleSheet(UPLOAD_ZONE_STYLE)
        self._staged: Path | None = None

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        self._icon = QLabel("+")
        self._icon.setObjectName("uploadIcon")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._icon)

        self._hint = QLabel("Drop an audio file here\nor click to browse  (.wav / .mp3)")
        self._hint.setObjectName("uploadHint")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._hint)

        self._name_label = QLabel("")
        self._name_label.setObjectName("uploadedName")
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.hide()
        layout.addWidget(self._name_label)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        from PyQt6.QtWidgets import QFileDialog

        filters = "Audio (%s)" % " ".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Upload audio file", "", filters
        )
        if path_str:
            self._stage_file(Path(path_str))

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(
                UPLOAD_ZONE_STYLE.replace(
                    "border: 3px dashed #7a7a90;",
                    "border: 3px dashed #5b8def;",
                )
            )

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self.setStyleSheet(UPLOAD_ZONE_STYLE)

    def dropEvent(self, event) -> None:  # noqa: N802
        self.setStyleSheet(UPLOAD_ZONE_STYLE)
        urls = event.mimeData().urls()
        if urls:
            self._stage_file(Path(urls[0].toLocalFile()))

    def _stage_file(self, path: Path) -> None:
        if not path.is_file():
            return
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        self._staged = path
        self._name_label.setText(path.name)
        self._name_label.show()
        self._icon.hide()
        self._hint.hide()
        self.file_staged.emit(path)

    @property
    def staged_path(self) -> Path | None:
        return self._staged

    def clear_staged(self) -> None:
        self._staged = None
        self._name_label.hide()
        self._name_label.clear()
        self._icon.show()
        self._hint.show()


class _ProfilePanel(QWidget):
    """Content for one status profile: subtitle, current track, upload zone, SWAP."""

    soundtrack_swapped = pyqtSignal()

    def __init__(self, assets_dir: Path, profile_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._assets_dir = assets_dir
        self._profile_id = profile_id
        self._display = display_name_for_profile(profile_id)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Subtitle
        subtitle = QLabel(self._display)
        subtitle.setObjectName("subtitleLabel")
        layout.addWidget(subtitle)

        # Current soundtrack bar
        self._track_bar = QFrame()
        self._track_bar.setObjectName("trackBar")
        self._track_bar.setStyleSheet(TRACK_BAR_STYLE)
        track_layout = QHBoxLayout(self._track_bar)
        track_layout.setContentsMargins(0, 0, 0, 0)
        self._current_label = QLabel("")
        self._current_label.setObjectName("currentTrackLabel")
        self._no_track_label = QLabel("No soundtrack loaded")
        self._no_track_label.setObjectName("noTrackLabel")
        track_layout.addWidget(self._current_label)
        track_layout.addWidget(self._no_track_label)
        track_layout.addStretch()
        layout.addWidget(self._track_bar)

        # Upload zone + SWAP row
        row = QHBoxLayout()
        row.setSpacing(12)

        self._upload_zone = _UploadZone()
        row.addWidget(self._upload_zone, stretch=1)

        self._swap_btn = QPushButton("SWAP")
        self._swap_btn.setFixedHeight(60)
        self._swap_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swap_btn.setEnabled(False)
        self._swap_btn.setStyleSheet(SWAP_DISABLED)
        self._swap_btn.clicked.connect(self._on_swap)
        row.addWidget(self._swap_btn)

        layout.addLayout(row)
        layout.addStretch()

        self._upload_zone.file_staged.connect(self._on_file_staged)
        self.refresh()

    def refresh(self) -> None:
        tracks = list_tracks(self._assets_dir, self._profile_id)
        if tracks:
            self._current_label.setText(f"Current:  {tracks[0].name}")
            self._current_label.show()
            self._no_track_label.hide()
        else:
            self._current_label.hide()
            self._no_track_label.show()

    def _on_file_staged(self, _path: Path) -> None:
        self._swap_btn.setEnabled(True)
        self._swap_btn.setStyleSheet(SWAP_ENABLED)

    def _on_swap(self) -> None:
        staged = self._upload_zone.staged_path
        if staged is None:
            return
        try:
            add_track(self._assets_dir, self._profile_id, staged)
        except (OSError, ValueError):
            return
        self._upload_zone.clear_staged()
        self._swap_btn.setEnabled(False)
        self._swap_btn.setStyleSheet(SWAP_DISABLED)
        self.refresh()
        self.soundtrack_swapped.emit()

    def set_assets_dir(self, assets_dir: Path) -> None:
        self._assets_dir = assets_dir
        self.refresh()

    def set_dark_mode(self, enabled: bool) -> None:
        """Re-apply dark/light styling for track bar and upload zone."""
        self._track_bar.setStyleSheet(TRACK_BAR_STYLE if enabled else LIGHT_TRACK_BAR_STYLE)
        self._upload_zone.setStyleSheet(UPLOAD_ZONE_STYLE if enabled else LIGHT_UPLOAD_ZONE_STYLE)
        self._swap_btn.setStyleSheet(
            SWAP_ENABLED if self._swap_btn.isEnabled() else (SWAP_DISABLED if enabled else SWAP_DISABLED)
        )


class UploadPage(QWidget):
    """Per-status soundtrack management with horizontal subpage tabs."""

    soundtrack_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("uploadPage")
        self.setStyleSheet(UPLOAD_STYLE)

        self._assets_dir: Path | None = None
        self._panels: dict[str, _ProfilePanel] = {}
        self._tab_map: dict[int, str] = {}  # index → profile_id

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(16)

        # ── Title ──
        title = QLabel("Customize Soundtracks")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        # ── Horizontal tab bar ──
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        tab_row.setContentsMargins(0, 0, 0, 0)

        self._tab_buttons: list[QPushButton] = []
        for idx, profile_id in enumerate(PROFILE_IDS):
            icon = PROFILE_ICONS.get(profile_id, "◯")
            btn = QPushButton(icon)
            btn.setToolTip(display_name_for_profile(profile_id))
            btn.setFixedWidth(44)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c, i=idx: self._switch_tab(i))
            tab_row.addWidget(btn)
            self._tab_buttons.append(btn)
            self._tab_map[idx] = profile_id

        tab_row.addStretch()
        root.addLayout(tab_row)

        # ── Thin separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2a2a30;")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # ── Subtitle (profile name shown on tab switch) ──
        self._tab_subtitle = QLabel("")
        self._tab_subtitle.setObjectName("tabSubtitle")
        root.addWidget(self._tab_subtitle)

        # ── Content stack ──
        self._content = QStackedWidget()
        root.addWidget(self._content, stretch=1)

        self._switch_tab(0)

    # ── Public API ──────────────────────────────────────────────

    def set_assets_dir(self, assets_dir: Path) -> None:
        self._assets_dir = assets_dir
        # Refresh or rebuild panels
        self._panels.clear()
        while self._content.count():
            self._content.removeWidget(self._content.widget(0))

        for profile_id in PROFILE_IDS:
            panel = _ProfilePanel(assets_dir, profile_id)
            panel.soundtrack_swapped.connect(self.soundtrack_changed.emit)
            self._panels[profile_id] = panel
            self._content.addWidget(panel)

        self._switch_tab(0)

    # ── Theme switching ─────────────────────────────────────────

    def set_dark_mode(self, enabled: bool) -> None:
        """Apply dark / light stylesheet to the upload page and children."""
        self._dark = enabled
        self.setStyleSheet(UPLOAD_STYLE if enabled else LIGHT_UPLOAD_STYLE)
        # Re-style tabs
        on = TAB_ACTIVE if enabled else LIGHT_TAB_ACTIVE
        off = TAB_BASE if enabled else LIGHT_TAB_BASE
        for i, btn in enumerate(self._tab_buttons):
            btn.setStyleSheet(on if i == self._tab_index else off)
        # Push to panels
        for panel in self._panels.values():
            panel.set_dark_mode(enabled)

    # ── Internal ────────────────────────────────────────────────

    def _switch_tab(self, index: int) -> None:
        if not self._tab_map:
            return
        self._tab_index = index
        self._content.setCurrentIndex(index)
        on = TAB_ACTIVE if getattr(self, '_dark', True) else LIGHT_TAB_ACTIVE
        off = TAB_BASE if getattr(self, '_dark', True) else LIGHT_TAB_BASE
        for i, btn in enumerate(self._tab_buttons):
            btn.setStyleSheet(on if i == index else off)
        # Show profile name in subtitle
        profile_id = self._tab_map.get(index)
        if profile_id and hasattr(self, "_tab_subtitle"):
            self._tab_subtitle.setText(display_name_for_profile(profile_id))

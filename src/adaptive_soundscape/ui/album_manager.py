"""Dialog to upload or delete songs in each scenario album."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from adaptive_soundscape.audio.album import (
    PROFILE_IDS,
    add_track,
    delete_track,
    display_name_for_profile,
    list_tracks,
)
from adaptive_soundscape.audio.loader import SUPPORTED_EXTENSIONS


EDITOR_STYLE = """
QDialog, QWidget {
    background-color: #1a1a1e;
    color: #e8e8ec;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #33333a;
    border-radius: 6px;
    background: #25252b;
}
QTabBar::tab {
    background: #2e2e36;
    color: #c8c8d0;
    padding: 8px 12px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: #3a5a8c;
    color: #ffffff;
}
QListWidget {
    background: #1a1a1e;
    border: 1px solid #44444d;
    border-radius: 4px;
}
QPushButton {
    background-color: #33333a;
    border: 1px solid #44444d;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton:hover { background-color: #3d3d46; }
QPushButton#dangerBtn {
    border-color: #8c3a3a;
}
QLabel#hint {
    color: #888894;
    font-size: 11px;
}
"""


class _AlbumTab(QWidget):
    changed = pyqtSignal()

    def __init__(
        self,
        assets_dir: Path,
        profile_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.assets_dir = assets_dir
        self.profile_id = profile_id
        self._paths: list[Path] = []

        layout = QVBoxLayout(self)
        hint = QLabel(
            "Songs in this album play randomly when the scenario is active. "
            "Supported formats: MP3, WAV."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._list = QListWidget()
        layout.addWidget(self._list)

        row = QHBoxLayout()
        self._upload_btn = QPushButton("Upload Audio…")
        self._delete_btn = QPushButton("Delete Selected")
        self._delete_btn.setObjectName("dangerBtn")
        row.addWidget(self._upload_btn)
        row.addWidget(self._delete_btn)
        row.addStretch()
        layout.addLayout(row)

        self._upload_btn.clicked.connect(self._upload)
        self._delete_btn.clicked.connect(self._delete)
        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        self._paths = list_tracks(self.assets_dir, self.profile_id)
        for path in self._paths:
            self._list.addItem(path.name)

    def _upload(self) -> None:
        filters = "Audio (%s)" % " ".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Upload audio for scenario", "", filters
        )
        if not path_str:
            return
        try:
            dest = add_track(self.assets_dir, self.profile_id, Path(path_str))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Upload failed", str(exc))
            return
        self.refresh()
        self.changed.emit()
        QMessageBox.information(self, "Uploaded", f"Added {dest.name} to the album.")

    def _delete(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._paths):
            QMessageBox.information(self, "Delete", "Select a track to delete.")
            return
        path = self._paths[row]
        if len(self._paths) <= 1:
            QMessageBox.warning(
                self,
                "Delete",
                "Each scenario album needs at least one song. "
                "Upload a replacement before deleting the last track.",
            )
            return
        confirm = QMessageBox.question(
            self,
            "Delete track",
            f"Delete “{path.name}” from this album?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_track(path)
        except OSError as exc:
            QMessageBox.warning(self, "Delete failed", str(exc))
            return
        self.refresh()
        self.changed.emit()


class AlbumManagerDialog(QDialog):
    """Manage per-scenario song albums."""

    albums_changed = pyqtSignal()

    def __init__(self, assets_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.assets_dir = assets_dir
        self.setWindowTitle("Manage Scenario Albums")
        self.setMinimumSize(560, 480)
        self.setStyleSheet(EDITOR_STYLE)

        root = QVBoxLayout(self)
        intro = QLabel(
            "Each work scenario has its own album. When that scenario is active, "
            "the system picks a song from the album at random."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self._tabs = QTabWidget()
        self._dirty = False
        for profile_id in PROFILE_IDS:
            tab = _AlbumTab(assets_dir, profile_id)
            tab.changed.connect(self._on_changed)
            self._tabs.addTab(tab, display_name_for_profile(profile_id))
        root.addWidget(self._tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        root.addWidget(buttons)

    def _on_changed(self) -> None:
        self._dirty = True
        self.albums_changed.emit()

    @classmethod
    def run(cls, assets_dir: Path, parent: QWidget | None = None) -> bool:
        """Show the dialog; return True if albums were modified."""
        dialog = cls(assets_dir, parent)
        dialog.exec()
        return dialog._dirty

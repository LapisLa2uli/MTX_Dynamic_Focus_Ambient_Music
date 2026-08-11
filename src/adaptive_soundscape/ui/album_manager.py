"""Dialog to upload/delete intensity loops and stem layers; generate AI layers."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from adaptive_soundscape.audio.album import (
    PROFILE_IDS,
    add_layer_track,
    add_track,
    delete_track,
    display_name_for_profile,
    list_songs,
)
from adaptive_soundscape.audio.demucs_client import DemucsClient
from adaptive_soundscape.audio.generate_layers import generate_and_install_layer
from adaptive_soundscape.audio.layer_mix import LAYER_IDS
from adaptive_soundscape.audio.loader import SUPPORTED_EXTENSIONS
from adaptive_soundscape.audio.music_manifest import (
    INTENSITY_DIRS,
    MusicIntensity,
    list_playable_tracks,
    load_manifest,
    migrate_songs_to_layered_stubs,
)
from adaptive_soundscape.audio.musicgen_client import MusicGenClient
from adaptive_soundscape.audio.separate_stems import separate_and_install_stems
from adaptive_soundscape.core.config import load_settings


class _StemSeparateThread(QThread):
    """Background Demucs separation so the UI stays responsive."""

    succeeded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(
        self,
        song_dir: Path,
        *,
        api_base_url: str,
        timeout_seconds: float,
        model: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._song_dir = song_dir
        self._api_base_url = api_base_url
        self._timeout_seconds = timeout_seconds
        self._model = model

    def run(self) -> None:
        try:
            client = DemucsClient(
                self._api_base_url, timeout_seconds=self._timeout_seconds
            )
            written = separate_and_install_stems(
                self._song_dir,
                client=client,
                model=self._model,
                force=False,
            )
            self.succeeded.emit([str(p) for p in written])
        except Exception as exc:
            self.failed.emit(str(exc))


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
QComboBox {
    background: #1a1a1e;
    border: 1px solid #44444d;
    border-radius: 4px;
    padding: 4px 8px;
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
        self._entries: list[tuple[str, Path]] = []

        layout = QVBoxLayout(self)
        hint = QLabel(
            "Default playback mixes stem layers (pad / harmony / melody_a / rhythm / …) "
            "by concentration. Discrete calm/focus/deep_focus loops remain as fallback. "
            "AI layers require the MusicGen sidecar on localhost:7862."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        song_row = QHBoxLayout()
        song_row.addWidget(QLabel("Song"))
        self._song_combo = QComboBox()
        song_row.addWidget(self._song_combo, stretch=1)
        layout.addLayout(song_row)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Bucket"))
        self._bucket_combo = QComboBox()
        self._bucket_combo.addItem("Stem layer", "layer")
        self._bucket_combo.addItem("Discrete intensity", "intensity")
        mode_row.addWidget(self._bucket_combo, stretch=1)
        layout.addLayout(mode_row)

        layer_row = QHBoxLayout()
        layer_row.addWidget(QLabel("Layer"))
        self._layer_combo = QComboBox()
        for lid in LAYER_IDS:
            self._layer_combo.addItem(lid, lid)
        layer_row.addWidget(self._layer_combo, stretch=1)
        layout.addLayout(layer_row)

        int_row = QHBoxLayout()
        int_row.addWidget(QLabel("Intensity"))
        self._intensity_combo = QComboBox()
        for name in INTENSITY_DIRS:
            self._intensity_combo.addItem(name.replace("_", " ").title(), name)
        idx = self._intensity_combo.findData("focus")
        if idx >= 0:
            self._intensity_combo.setCurrentIndex(idx)
        int_row.addWidget(self._intensity_combo, stretch=1)
        layout.addLayout(int_row)

        self._list = QListWidget()
        layout.addWidget(self._list)

        row = QHBoxLayout()
        self._upload_btn = QPushButton("Upload Audio…")
        self._new_song_btn = QPushButton("Upload as New Song…")
        self._generate_btn = QPushButton("Generate AI Layers")
        self._delete_btn = QPushButton("Delete Selected")
        self._delete_btn.setObjectName("dangerBtn")
        row.addWidget(self._upload_btn)
        row.addWidget(self._new_song_btn)
        row.addWidget(self._generate_btn)
        row.addWidget(self._delete_btn)
        row.addStretch()
        layout.addLayout(row)

        self._song_combo.currentIndexChanged.connect(self._reload_tracks)
        self._bucket_combo.currentIndexChanged.connect(self._on_bucket_changed)
        self._layer_combo.currentIndexChanged.connect(self._reload_tracks)
        self._intensity_combo.currentIndexChanged.connect(self._reload_tracks)
        self._upload_btn.clicked.connect(lambda: self._upload(new_song=False))
        self._new_song_btn.clicked.connect(lambda: self._upload(new_song=True))
        self._generate_btn.clicked.connect(self._generate_ai)
        self._delete_btn.clicked.connect(self._delete)
        self._on_bucket_changed()
        self.refresh_songs()

    def _on_bucket_changed(self) -> None:
        layered = self._bucket_combo.currentData() == "layer"
        self._layer_combo.setEnabled(layered)
        self._intensity_combo.setEnabled(not layered)
        self._generate_btn.setEnabled(layered)
        self._reload_tracks()

    def refresh_songs(self) -> None:
        current = self._song_combo.currentData()
        self._song_combo.blockSignals(True)
        self._song_combo.clear()
        songs = list_songs(self.assets_dir, self.profile_id)
        for song in songs:
            self._song_combo.addItem(song.name, str(song))
        self._song_combo.blockSignals(False)
        if current:
            idx = self._song_combo.findData(current)
            if idx >= 0:
                self._song_combo.setCurrentIndex(idx)
        self._reload_tracks()

    def _current_song_dir(self) -> Path | None:
        data = self._song_combo.currentData()
        if not data:
            return None
        path = Path(str(data))
        return path if path.is_dir() else None

    def _current_intensity(self) -> MusicIntensity:
        raw = str(self._intensity_combo.currentData() or "focus")
        try:
            return MusicIntensity(raw)
        except ValueError:
            return MusicIntensity.FOCUS

    def _reload_tracks(self) -> None:
        self._list.clear()
        self._entries = []
        song = self._current_song_dir()
        if song is None:
            return
        if self._bucket_combo.currentData() == "layer":
            manifest = load_manifest(song)
            if manifest is None:
                return
            layer_id = str(self._layer_combo.currentData() or "pad")
            path = manifest.resolve_layer_path(song, layer_id)
            if path is not None:
                entry = manifest.layers.get(layer_id)
                gen = " [AI]" if entry and entry.generated else ""
                label = f"{layer_id}{gen}  ({path.name})"
                self._list.addItem(label)
                self._entries.append((label, path))
            return
        intensity = self._current_intensity()
        for entry, path in list_playable_tracks(song, intensity):
            label = f"{entry.id}  ({path.name})"
            self._list.addItem(label)
            self._entries.append((label, path))

    def _upload(self, *, new_song: bool) -> None:
        filters = "Audio (%s)" % " ".join(f"*{ext}" for ext in SUPPORTED_EXTENSIONS)
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Upload audio for scenario", "", filters
        )
        if not path_str:
            return
        created_new_song = False
        try:
            if self._bucket_combo.currentData() == "layer":
                song = self._current_song_dir()
                if song is None or new_song:
                    # Create via intensity focus first, then add layer.
                    dest_focus = add_track(
                        self.assets_dir,
                        self.profile_id,
                        Path(path_str),
                        intensity=MusicIntensity.FOCUS,
                        song_id=None if new_song or song is None else song.name,
                    )
                    song_dir = dest_focus.parent.parent
                    dest = add_layer_track(
                        self.assets_dir,
                        self.profile_id,
                        Path(path_str),
                        layer_id=str(self._layer_combo.currentData() or "pad"),
                        song_id=song_dir.name,
                    )
                    created_new_song = True
                else:
                    dest = add_layer_track(
                        self.assets_dir,
                        self.profile_id,
                        Path(path_str),
                        layer_id=str(self._layer_combo.currentData() or "pad"),
                        song_id=song.name,
                    )
                    song_dir = song
            else:
                intensity = self._current_intensity()
                existing = self._current_song_dir()
                song_id = None if new_song else (
                    existing.name if existing is not None else None
                )
                created_new_song = new_song or existing is None
                dest = add_track(
                    self.assets_dir,
                    self.profile_id,
                    Path(path_str),
                    intensity=intensity,
                    song_id=song_id,
                )
                song_dir = dest.parent.parent
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Upload failed", str(exc))
            return
        self.refresh_songs()
        idx = self._song_combo.findData(str(song_dir))
        if idx >= 0:
            self._song_combo.setCurrentIndex(idx)
        self.changed.emit()
        QMessageBox.information(
            self,
            "Uploaded",
            f"Added {dest.name} to {song_dir.name}.",
        )
        if created_new_song:
            self._maybe_auto_separate(song_dir)

    def _maybe_auto_separate(self, song_dir: Path) -> None:
        """Run Demucs on a newly uploaded full-mix song (background thread)."""
        settings = load_settings()
        cfg = settings.stem_separation
        if not cfg.enabled or not cfg.auto_on_upload:
            return
        client = DemucsClient(cfg.api_base_url, timeout_seconds=cfg.timeout_seconds)
        try:
            client.health()
        except RuntimeError as exc:
            migrate_songs_to_layered_stubs(self.assets_dir)
            self.refresh_songs()
            self.changed.emit()
            QMessageBox.warning(
                self,
                "Stem separation skipped",
                f"{exc}\n\nStub layers were installed. Start services/demucs_api "
                "then run:\npython scripts/separate_album_stems.py",
            )
            return

        progress = QProgressDialog(
            f"Separating stems for {song_dir.name}…",
            None,
            0,
            0,
            self,
        )
        progress.setWindowTitle("Stem separation")
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.setModal(True)
        progress.show()

        thread = _StemSeparateThread(
            song_dir,
            api_base_url=cfg.api_base_url,
            timeout_seconds=cfg.timeout_seconds,
            model=cfg.model,
            parent=self,
        )
        self._stem_thread = thread

        def _on_ok(paths: list) -> None:
            progress.close()
            self.refresh_songs()
            self.changed.emit()
            QMessageBox.information(
                self,
                "Stems ready",
                f"Separated {len(paths)} base layers for {song_dir.name}.",
            )

        def _on_fail(message: str) -> None:
            progress.close()
            migrate_songs_to_layered_stubs(self.assets_dir)
            self.refresh_songs()
            self.changed.emit()
            QMessageBox.warning(
                self,
                "Stem separation failed",
                f"{message}\n\nStub layers were installed as a fallback.",
            )

        thread.succeeded.connect(_on_ok)
        thread.failed.connect(_on_fail)
        thread.start()

    def _generate_ai(self) -> None:
        song = self._current_song_dir()
        if song is None:
            QMessageBox.information(self, "Generate", "Select a song first.")
            return
        settings = load_settings()
        gen = settings.generative_layers
        if not gen.enabled:
            QMessageBox.warning(self, "Generate", "generative_layers.enabled is false.")
            return
        client = MusicGenClient(gen.api_base_url, timeout_seconds=gen.timeout_seconds)
        try:
            client.health()
        except RuntimeError as exc:
            QMessageBox.warning(self, "MusicGen offline", str(exc))
            return
        written: list[str] = []
        for layer_id in gen.output_layers:
            try:
                dest = generate_and_install_layer(
                    song,
                    scenario=self.profile_id,
                    layer_id=layer_id,
                    client=client,
                    model_size=gen.model_size,
                )
                written.append(dest.name)
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "Generate failed",
                    f"{layer_id}: {exc}",
                )
                return
        self.refresh_songs()
        self.changed.emit()
        QMessageBox.information(
            self,
            "Generated",
            "Wrote AI layers:\n" + "\n".join(written),
        )

    def _delete(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._entries):
            QMessageBox.information(self, "Delete", "Select a track to delete.")
            return
        _, path = self._entries[row]
        song = self._current_song_dir()
        if song is None:
            return
        remaining = 0
        for intensity in MusicIntensity:
            remaining += len(list_playable_tracks(song, intensity))
        manifest = load_manifest(song)
        if manifest is not None:
            remaining += len(manifest.playable_layer_paths(song))
        if remaining <= 1:
            QMessageBox.warning(
                self,
                "Delete",
                "Each song needs at least one playable file. "
                "Upload a replacement before deleting the last track.",
            )
            return
        confirm = QMessageBox.question(
            self,
            "Delete track",
            f"Delete “{path.name}” from this song?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_track(path)
            # Also prune layer entry if needed
            if manifest is not None:
                changed = False
                for lid, entry in list(manifest.layers.items()):
                    if (song / entry.src).resolve() == path.resolve():
                        del manifest.layers[lid]
                        changed = True
                if changed:
                    from adaptive_soundscape.audio.music_manifest import save_manifest

                    save_manifest(song, manifest)
        except OSError as exc:
            QMessageBox.warning(self, "Delete failed", str(exc))
            return
        self.refresh_songs()
        self.changed.emit()


class AlbumManagerDialog(QDialog):
    """Manage per-scenario nested song albums (layers + discrete intensity)."""

    albums_changed = pyqtSignal()

    def __init__(self, assets_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.assets_dir = assets_dir
        self.setWindowTitle("Manage Scenario Albums")
        self.setMinimumSize(680, 560)
        self.setStyleSheet(EDITOR_STYLE)

        root = QVBoxLayout(self)
        intro = QLabel(
            "Scenario → song family → stem layers (default) or discrete intensity loops "
            "(fallback). Concentration adjusts layer volumes; MusicGen can add texture / "
            "melody_b offline."
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
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.clicked.connect(self.accept)
        root.addWidget(buttons)

    def _on_changed(self) -> None:
        self._dirty = True
        self.albums_changed.emit()

    @classmethod
    def run(cls, assets_dir: Path, parent: QWidget | None = None) -> bool:
        dialog = cls(assets_dir, parent)
        dialog.exec()
        return dialog._dirty

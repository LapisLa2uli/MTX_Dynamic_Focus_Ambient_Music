"""Dialog to upload/delete intensity loops and stem layers; generate AI layers."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QStackedWidget,
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

# Profile → emoji icon (mirrors upload_page.PROFILE_ICONS)
PROFILE_ICONS: dict[str, str] = {
    "programming": "\U0001f5a5\ufe0f",
    "team_workflow": "\U0001f465",
    "reading_writing": "\U0001f4d6",
    "scientific": "\U0001f52c",
    "creative_design": "\U0001f3a8",
    "distraction": "\u26a0\ufe0f",
    "unknown": "\u25ef",
}

# ── Stylesheets ──────────────────────────────────────────────────────

EDITOR_STYLE = """
QDialog {
    background-color: #1a1a1e;
    color: #e8e8ec;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QWidget#advancedContent {
    background-color: #1a1a1e;
}
QScrollArea {
    border: none;
    background-color: #1a1a1e;
}
QScrollArea > QWidget > QWidget {
    background-color: #1a1a1e;
}
QStackedWidget {
    background-color: #1a1a1e;
}
QLabel#pageTitle {
    color: #e8e8ec;
    font-size: 18px;
    font-weight: 800;
}
QLabel#sectionLabel {
    color: #c0c0d0;
    font-size: 12px;
    font-weight: 700;
    padding-top: 4px;
}
QLabel#songCount {
    color: #5b8def;
    font-size: 12px;
    font-weight: 700;
}
QLabel#noTrackHint {
    color: #7a7a8a;
    font-size: 12px;
    font-weight: 700;
}
QLabel#hint {
    color: #888894;
    font-size: 11px;
    font-weight: 500;
}
QListWidget {
    background: #262632;
    border: 1px solid #3e3e50;
    border-radius: 6px;
    color: #d0d0e0;
    padding: 4px;
    font-size: 12px;
}
QComboBox {
    background: #262632;
    border: 1px solid #3e3e50;
    border-radius: 6px;
    padding: 5px 10px;
    color: #e0e0ec;
    font-size: 12px;
    font-weight: 600;
}
QComboBox::drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background: #2a2a36;
    border: 1px solid #3e3e50;
    color: #e0e0ec;
    selection-background-color: #3a5a8c;
}
QPushButton {
    background-color: #33333a;
    color: #e8e8ec;
    border: 1px solid #44444d;
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 700;
}
QPushButton:hover { background-color: #3d3d46; }
QPushButton:pressed { background-color: #2a2a32; }
QPushButton#dangerBtn {
    border-color: #8c3a3a;
}
QPushButton#dangerBtn:hover { background-color: #4a2a2a; }
QPushButton#uploadBtn {
    background-color: #5b8def;
    color: #ffffff;
    border: none;
}
QPushButton#uploadBtn:hover { background-color: #6b9dff; }
QPushButton#uploadBtn:pressed { background-color: #4a7dde; }
QPushButton#closeBtn {
    background-color: #2a2a34;
    color: #a0a0b0;
    border: 1px solid #3e3e50;
}
"""

LIGHT_EDITOR_STYLE = """
QDialog {
    background-color: #f5f5f8;
    color: #1a1a1e;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QWidget#advancedContent {
    background-color: #f5f5f8;
}
QScrollArea {
    border: none;
    background-color: #f5f5f8;
}
QScrollArea > QWidget > QWidget {
    background-color: #f5f5f8;
}
QStackedWidget {
    background-color: #f5f5f8;
}
QLabel#pageTitle {
    color: #1a1a1e;
    font-size: 18px;
    font-weight: 800;
}
QLabel#sectionLabel {
    color: #3a3a48;
    font-size: 12px;
    font-weight: 700;
    padding-top: 4px;
}
QLabel#songCount {
    color: #3d6fd4;
    font-size: 12px;
    font-weight: 700;
}
QLabel#noTrackHint {
    color: #808090;
    font-size: 12px;
    font-weight: 700;
}
QLabel#hint {
    color: #707080;
    font-size: 11px;
    font-weight: 500;
}
QListWidget {
    background: #eeeef2;
    border: 1px solid #c0c0c8;
    border-radius: 6px;
    color: #282830;
    padding: 4px;
    font-size: 12px;
}
QComboBox {
    background: #eeeef2;
    border: 1px solid #c0c0c8;
    border-radius: 6px;
    padding: 5px 10px;
    color: #282830;
    font-size: 12px;
    font-weight: 600;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #f0f0f4;
    border: 1px solid #c8c8d0;
    color: #282830;
    selection-background-color: #5b8def;
}
QPushButton {
    background-color: #e2e2e8;
    color: #282830;
    border: 1px solid #c0c0c8;
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 700;
}
QPushButton:hover { background-color: #d6d6de; }
QPushButton:pressed { background-color: #c8c8d2; }
QPushButton#dangerBtn {
    border-color: #cc5a5a;
    color: #b03030;
}
QPushButton#dangerBtn:hover { background-color: #f0d8d8; }
QPushButton#uploadBtn {
    background-color: #5b8def;
    color: #ffffff;
    border: none;
}
QPushButton#uploadBtn:hover { background-color: #6b9dff; }
QPushButton#uploadBtn:pressed { background-color: #4a7dde; }
QPushButton#closeBtn {
    background-color: #e2e2e8;
    color: #585868;
    border: 1px solid #c0c0c8;
}
"""

TAB_BASE = """
QPushButton {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: #70707a;
    font-size: 13px;
    font-weight: 700;
    padding: 6px 12px;
}
QPushButton:hover { color: #a0a0b0; }
"""

TAB_ACTIVE = """
QPushButton {
    background: transparent;
    border: none;
    border-bottom: 2px solid #5b8def;
    color: #e8e8ec;
    font-size: 13px;
    font-weight: 700;
    padding: 6px 12px;
}
"""

LIGHT_TAB_BASE = """
QPushButton {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: #808090;
    font-size: 13px;
    font-weight: 700;
    padding: 6px 12px;
}
QPushButton:hover { color: #404050; }
"""

LIGHT_TAB_ACTIVE = """
QPushButton {
    background: transparent;
    border: none;
    border-bottom: 2px solid #5b8def;
    color: #181820;
    font-size: 13px;
    font-weight: 700;
    padding: 6px 12px;
}
"""


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


class _AlbumTab(QWidget):
    """One scenario album tab: pick song → bucket → tracks → upload/delete/generate."""

    changed = pyqtSignal()

    def __init__(
        self,
        assets_dir: Path,
        profile_id: str,
        *,
        dark: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.assets_dir = assets_dir
        self.profile_id = profile_id
        self._dark = dark
        self._entries: list[tuple[str, Path]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(10)

        # ── hint label ──
        hint = QLabel(
            "Default playback mixes stem layers (pad / harmony / melody_a / rhythm / …) "
            "by concentration. Discrete calm / focus / deep_focus loops remain as "
            "fallback. AI layers require the MusicGen sidecar on localhost:7862."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setObjectName("hint")
        layout.addWidget(sep1)

        # ── song row ──
        song_row = QHBoxLayout()
        song_row.setSpacing(10)
        song_lbl = QLabel("\U0001f3b5  Song")
        song_lbl.setObjectName("sectionLabel")
        song_row.addWidget(song_lbl)
        self._song_combo = QComboBox()
        song_row.addWidget(self._song_combo, stretch=1)
        layout.addLayout(song_row)

        # ── bucket row ──
        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_lbl = QLabel("\U0001f4e6  Bucket")
        mode_lbl.setObjectName("sectionLabel")
        mode_row.addWidget(mode_lbl)
        self._bucket_combo = QComboBox()
        self._bucket_combo.addItem("\U0001f3b6  Stem layer", "layer")
        self._bucket_combo.addItem("\U0001f522  Discrete intensity", "intensity")
        mode_row.addWidget(self._bucket_combo, stretch=1)
        layout.addLayout(mode_row)

        # ── layer row ──
        layer_row = QHBoxLayout()
        layer_row.setSpacing(10)
        layer_lbl = QLabel("\U0001f50a  Layer")
        layer_lbl.setObjectName("sectionLabel")
        layer_row.addWidget(layer_lbl)
        self._layer_combo = QComboBox()
        for lid in LAYER_IDS:
            self._layer_combo.addItem(lid, lid)
        layer_row.addWidget(self._layer_combo, stretch=1)
        layout.addLayout(layer_row)

        # ── intensity row ──
        int_row = QHBoxLayout()
        int_row.setSpacing(10)
        int_lbl = QLabel("\U0001f4c8  Intensity")
        int_lbl.setObjectName("sectionLabel")
        int_row.addWidget(int_lbl)
        self._intensity_combo = QComboBox()
        for name in INTENSITY_DIRS:
            self._intensity_combo.addItem(name.replace("_", " ").title(), name)
        idx = self._intensity_combo.findData("focus")
        if idx >= 0:
            self._intensity_combo.setCurrentIndex(idx)
        int_row.addWidget(self._intensity_combo, stretch=1)
        layout.addLayout(int_row)

        # ── track list ──
        self._list = QListWidget()
        self._list.setMinimumHeight(100)
        layout.addWidget(self._list, stretch=1)

        # ── button row ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._upload_btn = QPushButton("\U0001f4c1  Upload Audio…")
        self._upload_btn.setObjectName("uploadBtn")
        self._new_song_btn = QPushButton("\U0001f195  Upload as New Song…")
        self._generate_btn = QPushButton("\U0001f9e0  Generate AI Layers")
        self._delete_btn = QPushButton("\U0001f5d1  Delete Selected")
        self._delete_btn.setObjectName("dangerBtn")
        btn_row.addWidget(self._upload_btn)
        btn_row.addWidget(self._new_song_btn)
        btn_row.addWidget(self._generate_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── connections ──
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
            self, "Uploaded", f"Added {dest.name} to {song_dir.name}."
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
                    self, "Generate failed", f"{layer_id}: {exc}"
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
            f"\u201c{path.name}\u201d from this song?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_track(path)
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
        self._dark = True
        self._tab_index = 0
        self.setWindowTitle("Manage Scenario Albums")
        self.setMinimumSize(700, 560)
        self.setObjectName("advancedDialog")
        self.setStyleSheet(EDITOR_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 16)
        root.setSpacing(12)

        # ── title row ──
        title = QLabel("Advanced Album Manager")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        intro = QLabel(
            "Scenario \u2192 song family \u2192 stem layers (default) or discrete "
            "intensity loops (fallback). Concentration adjusts layer volumes; "
            "MusicGen can add texture / melody_b offline."
        )
        intro.setWordWrap(True)
        intro.setObjectName("hint")
        root.addWidget(intro)

        # ── emoji tab buttons (matching upload page style) ──
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        tab_row.setContentsMargins(0, 0, 0, 0)

        self._tab_buttons: list[QPushButton] = []
        self._tab_ids: dict[int, str] = {}
        for idx, profile_id in enumerate(PROFILE_IDS):
            icon = PROFILE_ICONS.get(profile_id, "\u25ef")
            btn = QPushButton(icon)
            btn.setToolTip(display_name_for_profile(profile_id))
            btn.setFixedWidth(44)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c, i=idx: self._switch_tab(i))
            tab_row.addWidget(btn)
            self._tab_buttons.append(btn)
            self._tab_ids[idx] = profile_id

        tab_row.addStretch()
        root.addLayout(tab_row)

        # ── separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2a2a30;")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # ── subtitle ──
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("sectionLabel")
        root.addWidget(self._subtitle)

        # ── scrollable tab content ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("advancedContent")

        self._stack = QStackedWidget()
        self._dirty = False
        self._tabs: dict[str, _AlbumTab] = {}
        for profile_id in PROFILE_IDS:
            tab = _AlbumTab(assets_dir, profile_id, dark=self._dark)
            tab.changed.connect(self._on_changed)
            self._tabs[profile_id] = tab
            self._stack.addWidget(tab)

        scroll.setWidget(self._stack)
        root.addWidget(scroll, stretch=1)

        # ── close button ──
        close_row = QHBoxLayout()
        close_row.addStretch()
        self._close_btn = QPushButton("Close")
        self._close_btn.setObjectName("closeBtn")
        self._close_btn.setFixedWidth(90)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self.accept)
        close_row.addWidget(self._close_btn)
        root.addLayout(close_row)

        self._switch_tab(0)

    def _switch_tab(self, index: int) -> None:
        self._tab_index = index
        self._stack.setCurrentIndex(index)
        on = TAB_ACTIVE if self._dark else LIGHT_TAB_ACTIVE
        off = TAB_BASE if self._dark else LIGHT_TAB_BASE
        for i, btn in enumerate(self._tab_buttons):
            btn.setStyleSheet(on if i == index else off)
        profile_id = self._tab_ids.get(index, "")
        if profile_id:
            self._subtitle.setText(display_name_for_profile(profile_id))

    def _on_changed(self) -> None:
        self._dirty = True
        self.albums_changed.emit()

    def set_dark_mode(self, enabled: bool) -> None:
        """Re-apply dark / light stylesheet and tab button styles."""
        self._dark = enabled
        self.setStyleSheet(EDITOR_STYLE if enabled else LIGHT_EDITOR_STYLE)
        self._switch_tab(self._tab_index)

    @classmethod
    def run(
        cls, assets_dir: Path, parent: QWidget | None = None, *, dark: bool = True
    ) -> bool:
        dialog = cls(assets_dir, parent)
        if not dark:
            dialog.set_dark_mode(False)
        dialog.exec()
        return dialog._dirty

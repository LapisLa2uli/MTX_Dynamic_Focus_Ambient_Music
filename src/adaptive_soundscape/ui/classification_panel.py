"""Right-side panel listing unclassified windows for per-item confirmation."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from adaptive_soundscape.context.user_mappings import CONFIGURABLE_CONTEXTS
from adaptive_soundscape.core.events import WorkContext
from adaptive_soundscape.core.i18n import theme_label, tr

PANEL_WIDTH = 300

DARK_STYLE = """
QWidget#classificationPanel {
    background-color: #16161a;
    border-left: 1px solid #2a2a30;
}
QLabel#classifyPanelTitle {
    color: #e8e8ec;
    font-size: 13px;
    font-weight: 700;
}
QLabel#classifyPanelHint, QLabel#classifyEmpty {
    color: #8a8a98;
    font-size: 11px;
}
QFrame#classifyRow {
    background-color: #1e1e24;
    border: 1px solid #2e2e36;
    border-radius: 8px;
}
QLabel#classifyProcess {
    color: #e0e0e8;
    font-size: 12px;
    font-weight: 700;
}
QLabel#classifyTitle, QLabel#classifySuggest {
    color: #9a9aac;
    font-size: 11px;
}
QComboBox#classifyCombo {
    background-color: #25252b;
    border: 1px solid #3a3a44;
    border-radius: 4px;
    padding: 4px 8px;
    color: #e8e8ec;
    font-size: 11px;
}
QComboBox#classifyCombo QAbstractItemView {
    background-color: #1a1a1e;
    color: #e8e8ec;
    selection-background-color: #3a5a8c;
}
QPushButton#classifySave {
    background-color: #3a5a8c;
    border: 1px solid #5b8def;
    border-radius: 4px;
    padding: 4px 10px;
    color: #e8e8ec;
    font-size: 11px;
    font-weight: 700;
}
QPushButton#classifySave:hover { background-color: #4a6ea8; }
QPushButton#classifyClose {
    background: transparent;
    border: none;
    color: #8a8a98;
    font-size: 16px;
}
QPushButton#classifyClose:hover { color: #e8e8ec; }
"""

LIGHT_STYLE = """
QWidget#classificationPanel {
    background-color: #ededf2;
    border-left: 1px solid #d0d0d8;
}
QLabel#classifyPanelTitle {
    color: #1a1a22;
    font-size: 13px;
    font-weight: 700;
}
QLabel#classifyPanelHint, QLabel#classifyEmpty {
    color: #5a5a6c;
    font-size: 11px;
}
QFrame#classifyRow {
    background-color: #f7f7fb;
    border: 1px solid #d8d8e0;
    border-radius: 8px;
}
QLabel#classifyProcess {
    color: #1a1a22;
    font-size: 12px;
    font-weight: 700;
}
QLabel#classifyTitle, QLabel#classifySuggest {
    color: #5a5a6c;
    font-size: 11px;
}
QComboBox#classifyCombo {
    background-color: #ffffff;
    border: 1px solid #c8c8d0;
    border-radius: 4px;
    padding: 4px 8px;
    color: #1a1a1e;
    font-size: 11px;
}
QComboBox#classifyCombo QAbstractItemView {
    background-color: #ffffff;
    color: #1a1a1e;
    selection-background-color: #5b8def;
}
QPushButton#classifySave {
    background-color: #3a5a8c;
    border: 1px solid #5b8def;
    border-radius: 4px;
    padding: 4px 10px;
    color: #e8e8ec;
    font-size: 11px;
    font-weight: 700;
}
QPushButton#classifySave:hover { background-color: #4a6ea8; }
QPushButton#classifyClose {
    background: transparent;
    border: none;
    color: #5a5a6c;
    font-size: 16px;
}
QPushButton#classifyClose:hover { color: #1a1a22; }
"""


class ClassificationRow(QFrame):
    saved = pyqtSignal(str, str, object)  # process, title, WorkContext

    def __init__(
        self,
        *,
        process_name: str,
        window_title: str,
        suggested: WorkContext,
        confidence: float,
        source: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("classifyRow")
        self.process_name = process_name
        self.window_title = window_title
        self._suggested = suggested

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        proc = QLabel(process_name or tr("classify_no_process"))
        proc.setObjectName("classifyProcess")
        proc.setWordWrap(True)
        layout.addWidget(proc)

        title = QLabel(window_title or tr("classify_no_title"))
        title.setObjectName("classifyTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        hint = QLabel(self._suggest_text(suggested, confidence, source))
        hint.setObjectName("classifySuggest")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._combo = QComboBox()
        self._combo.setObjectName("classifyCombo")
        for ctx in CONFIGURABLE_CONTEXTS:
            self._combo.addItem(theme_label(ctx.value), ctx.value)
        if suggested != WorkContext.UNKNOWN:
            idx = self._combo.findData(suggested.value)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
        save = QPushButton(tr("classify_save"))
        save.setObjectName("classifySave")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self._on_save)
        row.addWidget(self._combo, stretch=1)
        row.addWidget(save)
        layout.addLayout(row)

    @staticmethod
    def _suggest_text(suggested: WorkContext, confidence: float, source: str) -> str:
        if suggested == WorkContext.UNKNOWN:
            return tr("classify_no_guess")
        return tr("classify_suggested").format(
            name=theme_label(suggested.value),
            source=source,
            pct=f"{confidence:.0%}",
        )

    def _on_save(self) -> None:
        raw = self._combo.currentData()
        try:
            ctx = WorkContext(str(raw)) if raw is not None else WorkContext.UNKNOWN
        except ValueError:
            ctx = WorkContext.UNKNOWN
        self.saved.emit(self.process_name, self.window_title, ctx)


class ClassificationPanel(QWidget):
    """Docked list of unclassified windows; each row saves independently."""

    item_saved = pyqtSignal(str, str, object)
    closed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("classificationPanel")
        self.setFixedWidth(PANEL_WIDTH)
        self._dark = True
        self._rows: list[ClassificationRow] = []
        self._build()
        self.set_dark_mode(True)
        self.hide()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 14, 12, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        self._title = QLabel(tr("classify_panel_title"))
        self._title.setObjectName("classifyPanelTitle")
        self._title.setWordWrap(True)
        header.addWidget(self._title, stretch=1)
        close = QPushButton("×")
        close.setObjectName("classifyClose")
        close.setFixedSize(22, 22)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.hide_panel)
        header.addWidget(close, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        self._hint = QLabel(tr("classify_panel_hint"))
        self._hint.setObjectName("classifyPanelHint")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_host = QWidget()
        self._list_host.setObjectName("classifyListHost")
        self._list = QVBoxLayout(self._list_host)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(8)
        self._list.addStretch(1)
        self._scroll.setWidget(self._list_host)
        root.addWidget(self._scroll, stretch=1)

        self._empty = QLabel(tr("classify_empty"))
        self._empty.setObjectName("classifyEmpty")
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._empty)
        self._empty.hide()

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def set_dark_mode(self, enabled: bool) -> None:
        self._dark = bool(enabled)
        self.setStyleSheet(DARK_STYLE if self._dark else LIGHT_STYLE)

    def set_language(self) -> None:
        self._title.setText(tr("classify_panel_title"))
        self._hint.setText(tr("classify_panel_hint"))
        self._empty.setText(tr("classify_empty"))

    def show_panel(self) -> None:
        self.show()
        self.raise_()

    def hide_panel(self) -> None:
        was = self.isVisible()
        self.hide()
        if was:
            self.closed.emit()

    def set_items(self, items: list[dict]) -> None:
        """Replace the list. Each dict: process_name, window_title, suggested, confidence, source."""
        while self._rows:
            row = self._rows.pop()
            self._list.removeWidget(row)
            row.deleteLater()

        for item in items:
            suggested = item.get("suggested", WorkContext.UNKNOWN)
            if not isinstance(suggested, WorkContext):
                try:
                    suggested = WorkContext(str(suggested))
                except ValueError:
                    suggested = WorkContext.UNKNOWN
            row = ClassificationRow(
                process_name=str(item.get("process_name") or ""),
                window_title=str(item.get("window_title") or ""),
                suggested=suggested,
                confidence=float(item.get("confidence") or 0.0),
                source=str(item.get("source") or ""),
            )
            row.saved.connect(self.item_saved.emit)
            self._list.insertWidget(self._list.count() - 1, row)
            self._rows.append(row)

        empty = not self._rows
        self._empty.setVisible(empty)
        self._scroll.setVisible(not empty)

    @property
    def row_count(self) -> int:
        return len(self._rows)

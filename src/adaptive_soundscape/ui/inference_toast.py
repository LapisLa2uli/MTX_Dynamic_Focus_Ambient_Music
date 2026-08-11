"""In-window panel for confirming inferred misc-window classifications."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from adaptive_soundscape.core.events import WorkContext
from adaptive_soundscape.context.user_mappings import CONFIGURABLE_CONTEXTS


TOAST_STYLE = """
QWidget#inferenceToast {
    background-color: #25252b;
    color: #e8e8ec;
    border: 1px solid #44444d;
    border-radius: 10px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
}
QLabel#toastTitle {
    font-size: 13px;
    font-weight: 700;
}
QLabel#toastMeta {
    color: #a0a0aa;
}
QComboBox {
    background-color: #1a1a1e;
    border: 1px solid #44444d;
    border-radius: 4px;
    padding: 4px 8px;
    color: #e8e8ec;
}
QPushButton {
    background-color: #33333a;
    border: 1px solid #44444d;
    border-radius: 6px;
    padding: 6px 12px;
    color: #e8e8ec;
}
QPushButton#confirmBtn {
    background-color: #3a5a8c;
    border-color: #5b8def;
}
QPushButton:hover { background-color: #3d3d46; }
QPushButton#confirmBtn:hover { background-color: #4a6ea8; }
"""

LIGHT_TOAST_STYLE = """
QWidget#inferenceToast {
    background-color: #ffffff;
    color: #1a1a1e;
    border: 1px solid #c0c0c8;
    border-radius: 10px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
}
QLabel#toastTitle {
    font-size: 13px;
    font-weight: 700;
}
QLabel#toastMeta {
    color: #686878;
}
QComboBox {
    background-color: #f5f5f8;
    border: 1px solid #c0c0c8;
    border-radius: 4px;
    padding: 4px 8px;
    color: #1a1a1e;
}
QPushButton {
    background-color: #e0e0e5;
    border: 1px solid #c0c0c8;
    border-radius: 6px;
    padding: 6px 12px;
    color: #1a1a1e;
}
QPushButton#confirmBtn {
    background-color: #3a5a8c;
    border-color: #5b8def;
    color: #e8e8ec;
}
QPushButton:hover { background-color: #d0d0d8; }
QPushButton#confirmBtn:hover { background-color: #4a6ea8; }
"""


def _label_for(ctx: WorkContext) -> str:
    return ctx.value.replace("_", " ").title()


class InferenceToast(QWidget):
    """Non-modal in-app notice: confirm or correct an inferred category."""

    confirmed = pyqtSignal(str, str, object)  # process, title, WorkContext
    dismissed = pyqtSignal(str)  # process key

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inferenceToast")
        # Child overlay — stays inside the main window (not a separate popup).
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(TOAST_STYLE)
        self.setFixedWidth(340)
        self.hide()

        self._process = ""
        self._title = ""
        self._process_key = ""
        self._dark = True

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        title = QLabel("Unknown window — confirm category")
        title.setObjectName("toastTitle")
        root.addWidget(title)

        self._process_label = QLabel("")
        self._process_label.setObjectName("toastMeta")
        self._process_label.setWordWrap(True)
        root.addWidget(self._process_label)

        self._title_label = QLabel("")
        self._title_label.setObjectName("toastMeta")
        self._title_label.setWordWrap(True)
        root.addWidget(self._title_label)

        self._hint = QLabel("")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        self._combo = QComboBox()
        for ctx in CONFIGURABLE_CONTEXTS:
            # Store enum values as strings so QVariant round-trips reliably.
            self._combo.addItem(_label_for(ctx), ctx.value)
        root.addWidget(self._combo)

        buttons = QHBoxLayout()
        self._dismiss_btn = QPushButton("Dismiss")
        self._confirm_btn = QPushButton("Save")
        self._confirm_btn.setObjectName("confirmBtn")
        buttons.addWidget(self._dismiss_btn)
        buttons.addStretch()
        buttons.addWidget(self._confirm_btn)
        root.addLayout(buttons)

        self._confirm_btn.clicked.connect(self._on_confirm)
        self._dismiss_btn.clicked.connect(self._on_dismiss)

        if parent is not None:
            parent.installEventFilter(self)

    def set_dark_mode(self, enabled: bool) -> None:
        self._dark = enabled
        self.setStyleSheet(TOAST_STYLE if enabled else LIGHT_TOAST_STYLE)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            if self.isVisible():
                self._reposition()
        return super().eventFilter(watched, event)

    def show_inference(
        self,
        *,
        process_name: str,
        window_title: str,
        suggested: WorkContext,
        confidence: float,
        source: str,
    ) -> None:
        self._process = process_name
        self._title = window_title
        self._process_key = _process_key(process_name)

        proc_display = process_name or "(no process)"
        title_display = window_title or "(no title)"
        self._process_label.setText(f"Process: {proc_display}")
        self._title_label.setText(f"Title: {title_display}")

        if suggested != WorkContext.UNKNOWN:
            self._hint.setText(
                f"Suggested: {_label_for(suggested)} "
                f"({source}, confidence {confidence:.0%}). "
                "Confirm or pick another category to remember this app."
            )
            idx = self._combo.findData(suggested.value)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
        else:
            self._hint.setText(
                "No confident guess. Pick the category this window belongs to."
            )

        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()

    def is_showing_for(self, process_name: str) -> bool:
        return self.isVisible() and self._process_key == _process_key(process_name)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        margin = 16
        # Sit above the status line area inside the content host.
        x = max(margin, parent.width() - self.width() - margin)
        y = max(margin, parent.height() - self.height() - margin)
        self.move(x, y)

    def _on_confirm(self) -> None:
        raw = self._combo.currentData()
        try:
            ctx = WorkContext(str(raw)) if raw is not None else WorkContext.UNKNOWN
        except ValueError:
            ctx = WorkContext.UNKNOWN
        self.confirmed.emit(self._process, self._title, ctx)
        self.hide()

    def _on_dismiss(self) -> None:
        self.dismissed.emit(self._process_key)
        self.hide()


def _process_key(process_name: str) -> str:
    key = process_name.lower().strip()
    if key.endswith(".exe"):
        key = key[:-4]
    return key

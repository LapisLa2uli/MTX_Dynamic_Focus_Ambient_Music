"""Reusable UI widgets."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget


class StatusCard(QFrame):
    """Dark card showing a label and value."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        self._title = QLabel(title)
        self._title.setObjectName("cardTitle")
        self._value = QLabel("—")
        self._value.setObjectName("cardValue")
        layout.addWidget(self._title)
        layout.addWidget(self._value)

    def set_value(self, text: str) -> None:
        self._value.setText(text)


class FocusMeter(QWidget):
    """Horizontal focus score meter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self._label = QLabel("Focus")
        self._score_label = QLabel("0.00")
        row.addWidget(self._label)
        row.addStretch()
        row.addWidget(self._score_label)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        layout.addLayout(row)
        layout.addWidget(self._bar)

    def set_score(self, score: float) -> None:
        pct = int(max(0.0, min(1.0, score)) * 100)
        self._bar.setValue(pct)
        self._score_label.setText(f"{score:.2f}")

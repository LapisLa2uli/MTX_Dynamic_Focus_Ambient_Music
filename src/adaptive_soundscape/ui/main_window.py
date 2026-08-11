"""Main application window."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt

from adaptive_soundscape.core.events import FocusState, WorkContext
from adaptive_soundscape.ui.widgets import FocusMeter, StatusCard


DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #1a1a1e;
    color: #e8e8ec;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QFrame#statusCard {
    background-color: #25252b;
    border: 1px solid #33333a;
    border-radius: 8px;
    padding: 8px;
}
QLabel#cardTitle {
    color: #888894;
    font-size: 11px;
}
QLabel#cardValue {
    font-size: 15px;
    font-weight: 600;
}
QLabel#cardSub {
    color: #888894;
    font-size: 11px;
}
QProgressBar {
    background-color: #2e2e36;
    border: none;
    border-radius: 4px;
    height: 8px;
}
QProgressBar::chunk {
    background-color: #5b8def;
    border-radius: 4px;
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
QSlider::groove:horizontal {
    height: 6px;
    background: #2e2e36;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #5b8def;
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QCheckBox { spacing: 8px; }
"""


class MainWindow(QMainWindow):
    """Dark minimal dashboard for adaptive soundscape."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Adaptive Cognitive Soundscape")
        self.setMinimumSize(520, 520)
        self.setStyleSheet(DARK_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        header = QLabel("Adaptive Soundscape")
        header.setStyleSheet("font-size: 18px; font-weight: 700;")
        root.addWidget(header)

        cards = QHBoxLayout()
        self._context_card = StatusCard("Context")
        self._focus_state_card = StatusCard("Focus State")
        self._profile_card = StatusCard("Active Profile")
        self._music_card = StatusCard("Music State")
        cards.addWidget(self._context_card)
        cards.addWidget(self._focus_state_card)
        cards.addWidget(self._profile_card)
        cards.addWidget(self._music_card)
        root.addLayout(cards)

        self._music_sub = QLabel("")
        self._music_sub.setObjectName("cardSub")
        self._music_sub.setWordWrap(True)
        root.addWidget(self._music_sub)

        self._focus_meter = FocusMeter()
        root.addWidget(self._focus_meter)

        override_row = QHBoxLayout()
        self._override_check = QCheckBox("Manual override")
        self._context_combo = QComboBox()
        for ctx in WorkContext:
            if ctx != WorkContext.UNKNOWN:
                self._context_combo.addItem(ctx.value.replace("_", " ").title(), ctx)
        override_row.addWidget(self._override_check)
        override_row.addWidget(self._context_combo, stretch=1)
        root.addLayout(override_row)

        sens_row = QHBoxLayout()
        sens_row.addWidget(QLabel("Sensitivity"))
        self._sensitivity_spin = QDoubleSpinBox()
        self._sensitivity_spin.setRange(0.2, 2.0)
        self._sensitivity_spin.setSingleStep(0.1)
        self._sensitivity_spin.setValue(1.0)
        sens_row.addWidget(self._sensitivity_spin)
        root.addLayout(sens_row)

        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Music volume"))
        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(75)
        self._mute_check = QCheckBox("Mute")
        vol_row.addWidget(self._volume_slider, stretch=1)
        vol_row.addWidget(self._mute_check)
        root.addLayout(vol_row)

        privacy_label = QLabel("Privacy")
        privacy_label.setStyleSheet("font-weight: 600; margin-top: 8px;")
        root.addWidget(privacy_label)

        self._title_check = QCheckBox("Collect window titles (metadata only)")
        self._title_check.setChecked(True)
        self._process_check = QCheckBox("Collect process names")
        self._process_check.setChecked(True)
        self._log_check = QCheckBox("Enable activity logging (off by default)")
        self._log_check.setChecked(False)
        root.addWidget(self._title_check)
        root.addWidget(self._process_check)
        root.addWidget(self._log_check)

        btn_row = QHBoxLayout()
        self._audio_btn = QPushButton("Start Audio")
        self._categories_btn = QPushButton("Configure Categories")
        self._albums_btn = QPushButton("Manage Albums")
        btn_row.addWidget(self._audio_btn)
        btn_row.addWidget(self._categories_btn)
        btn_row.addWidget(self._albums_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #c07070; font-size: 12px;")
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)
        root.addStretch()

    def set_status_message(self, message: str) -> None:
        self._status_label.setText(message)

    def update_status(
        self,
        *,
        context: WorkContext,
        focus_state: FocusState,
        focus_score: float,
        profile_name: str,
        music_state: str = "—",
        music_detail: str = "",
    ) -> None:
        self._context_card.set_value(context.value.replace("_", " ").title())
        self._focus_state_card.set_value(focus_state.value.replace("_", " ").title())
        self._profile_card.set_value(profile_name)
        self._music_card.set_value(music_state)
        self._music_sub.setText(music_detail)
        self._focus_meter.set_score(focus_score)

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

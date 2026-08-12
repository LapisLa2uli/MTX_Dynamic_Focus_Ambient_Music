"""Minimal go/no-go attention probe dialog."""

from __future__ import annotations

import random
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from adaptive_soundscape.focus_index.models import AttentionProbeEvent
from adaptive_soundscape.focus_index.probes import ProbeSessionResult, ProbeTrial


class GoNoGoProbeDialog(QDialog):
    """Short go/no-go block. Space/click on green (go), withhold on red (no-go)."""

    def __init__(
        self,
        parent=None,
        *,
        task_profile: str = "default",
        trials: int = 20,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Attention Probe")
        self.setModal(True)
        self.resize(420, 280)
        self._task_profile = task_profile
        self._n_trials = max(8, int(trials))
        self._trials: list[ProbeTrial] = []
        self._pending_go: bool | None = None
        self._stimulus_at: float | None = None
        self._responded = False
        self._result_event: AttentionProbeEvent | None = None

        layout = QVBoxLayout(self)
        self._info = QLabel(
            "Press Space or the button on GREEN (go).\n"
            "Do nothing on RED (no-go)."
        )
        self._info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._info)

        self._stimulus = QLabel("Ready")
        self._stimulus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stimulus.setStyleSheet(
            "font-size: 28px; font-weight: 700; padding: 36px; "
            "background:#2a2a34; border-radius: 12px; color:#e8e8ec;"
        )
        layout.addWidget(self._stimulus)

        rating_row = QHBoxLayout()
        rating_row.addWidget(QLabel("Self-rating (1–7, optional):"))
        self._rating = QSpinBox()
        self._rating.setRange(0, 7)
        self._rating.setSpecialValueText("—")
        self._rating.setValue(0)
        rating_row.addWidget(self._rating)
        rating_row.addStretch()
        layout.addLayout(rating_row)

        btn_row = QHBoxLayout()
        self._go_btn = QPushButton("Respond")
        self._go_btn.clicked.connect(self._on_respond)
        btn_row.addWidget(self._go_btn)
        self._start_btn = QPushButton("Start")
        self._start_btn.clicked.connect(self._start)
        btn_row.addWidget(self._start_btn)
        layout.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_trial_timeout)

    def result_event(self) -> AttentionProbeEvent | None:
        return self._result_event

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return):
            self._on_respond()
            return
        super().keyPressEvent(event)

    def _start(self) -> None:
        self._trials.clear()
        self._start_btn.setEnabled(False)
        self._next_trial()

    def _next_trial(self) -> None:
        if len(self._trials) >= self._n_trials:
            self._finish()
            return
        self._responded = False
        self._pending_go = random.random() < 0.7
        color = "#3d9e6f" if self._pending_go else "#c05050"
        label = "GO" if self._pending_go else "NO-GO"
        self._stimulus.setText(label)
        self._stimulus.setStyleSheet(
            f"font-size: 28px; font-weight: 700; padding: 36px; "
            f"background:{color}; border-radius: 12px; color:#ffffff;"
        )
        self._stimulus_at = time.perf_counter()
        self._timer.start(900)

    def _on_respond(self) -> None:
        if self._pending_go is None or self._responded:
            return
        self._responded = True
        self._timer.stop()
        rt = None
        if self._stimulus_at is not None:
            rt = (time.perf_counter() - self._stimulus_at) * 1000.0
        self._trials.append(
            ProbeTrial(is_go=bool(self._pending_go), responded=True, reaction_ms=rt)
        )
        self._pending_go = None
        QTimer.singleShot(250, self._next_trial)

    def _on_trial_timeout(self) -> None:
        if self._pending_go is None or self._responded:
            return
        self._trials.append(
            ProbeTrial(is_go=bool(self._pending_go), responded=False, reaction_ms=None)
        )
        self._pending_go = None
        QTimer.singleShot(200, self._next_trial)

    def _finish(self) -> None:
        rating = self._rating.value()
        session = ProbeSessionResult(
            trials=list(self._trials),
            self_rating=rating if rating > 0 else None,
            task_profile=self._task_profile,
        )
        self._result_event = session.to_event()
        self._stimulus.setText("Done")
        self._info.setText(
            f"Accuracy: {self._result_event.accuracy:.0%}. Closing…"
        )
        QTimer.singleShot(700, self.accept)

    @classmethod
    def run(
        cls, parent=None, *, task_profile: str = "default"
    ) -> AttentionProbeEvent | None:
        dlg = cls(parent, task_profile=task_profile)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.result_event()
        return None

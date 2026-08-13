"""Always-on-top mini HUD: play/stop, focus meter, Pomodoro remaining."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)


class MiniOverlay(QWidget):
    """Draggable, resizable HUD parked on the top-right of the screen."""

    play_toggled = pyqtSignal()
    hide_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("miniOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(188, 78)
        self.setMaximumSize(420, 180)
        self.resize(228, 92)
        self._dark = True
        self._running = False
        self._drag_origin: QPoint | None = None
        self._build()
        self._apply_style()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._play = QPushButton("▶")
        self._play.setObjectName("miniPlay")
        self._play.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play.setFixedSize(36, 36)
        self._play.clicked.connect(self.play_toggled.emit)
        top.addWidget(self._play)

        col = QVBoxLayout()
        col.setSpacing(3)
        self._focus_label = QLabel("Focus  0%")
        self._focus_label.setObjectName("miniFocusLabel")
        self._bar = QProgressBar()
        self._bar.setObjectName("miniFocusBar")
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(7)
        col.addWidget(self._focus_label)
        col.addWidget(self._bar)
        top.addLayout(col, stretch=1)

        self._close = QPushButton("×")
        self._close.setObjectName("miniClose")
        self._close.setFixedSize(18, 18)
        self._close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close.clicked.connect(self.hide_requested.emit)
        top.addWidget(self._close, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(top)

        bottom = QHBoxLayout()
        self._pomo = QLabel("Pomodoro  —")
        self._pomo.setObjectName("miniPomo")
        bottom.addWidget(self._pomo)
        bottom.addStretch(1)
        grip = QSizeGrip(self)
        grip.setFixedSize(14, 14)
        bottom.addWidget(grip, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        root.addLayout(bottom)

    def _apply_style(self) -> None:
        if self._dark:
            bg, fg, muted, accent, btn = (
                "rgba(22, 22, 28, 220)",
                "#e8e8ec",
                "#9a9aac",
                "#5b8def",
                "#2a2a36",
            )
        else:
            bg, fg, muted, accent, btn = (
                "rgba(248, 248, 252, 230)",
                "#1a1a22",
                "#5a5a6c",
                "#3d6fd4",
                "#ececf2",
            )
        self.setStyleSheet(
            f"""
            QWidget#miniOverlay {{
                background: {bg};
                border: 1px solid {accent};
                border-radius: 14px;
            }}
            QLabel#miniFocusLabel {{
                color: {fg};
                font-size: 11px;
                font-weight: 700;
            }}
            QLabel#miniPomo {{
                color: {muted};
                font-size: 10px;
                font-weight: 600;
            }}
            QProgressBar#miniFocusBar {{
                background: {btn};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar#miniFocusBar::chunk {{
                background: {accent};
                border-radius: 3px;
            }}
            QPushButton#miniPlay {{
                background: {btn};
                color: {fg};
                border: 1px solid {accent};
                border-radius: 18px;
                font-size: 13px;
                font-weight: 800;
            }}
            QPushButton#miniPlay:hover {{
                background: {accent};
                color: #ffffff;
            }}
            QPushButton#miniClose {{
                background: transparent;
                color: {muted};
                border: none;
                font-size: 14px;
            }}
            QPushButton#miniClose:hover {{ color: {fg}; }}
            """
        )

    def set_dark_mode(self, enabled: bool) -> None:
        self._dark = bool(enabled)
        self._apply_style()
        self.update()

    def set_running(self, running: bool) -> None:
        self._running = bool(running)
        self._play.setText("■" if self._running else "▶")

    def set_focus(self, score: float) -> None:
        pct = int(max(0.0, min(1.0, float(score))) * 100)
        self._bar.setValue(pct)
        self._focus_label.setText(f"Focus  {pct}%")

    def set_pomodoro(self, *, active: bool, label: str = "") -> None:
        if not active:
            self._pomo.setText("Pomodoro  —")
            return
        self._pomo.setText(label or "Pomodoro")

    def place_top_right(self, margin: int = 16) -> None:
        screen = self.screen()
        if screen is None:
            from PyQt6.QtWidgets import QApplication

            screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - self.width() - margin, geo.top() + margin)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N803
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N803
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N803
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(228, 92)

    def paintEvent(self, event) -> None:  # noqa: N803
        # Draw rounded chrome so WA_TranslucentBackground still has a body.
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._dark:
            fill = QColor(22, 22, 28, 220)
            edge = QColor(91, 141, 239, 160)
        else:
            fill = QColor(248, 248, 252, 230)
            edge = QColor(61, 111, 212, 140)
        p.setBrush(fill)
        p.setPen(QPen(edge, 1.2))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)
        p.end()
        super().paintEvent(event)

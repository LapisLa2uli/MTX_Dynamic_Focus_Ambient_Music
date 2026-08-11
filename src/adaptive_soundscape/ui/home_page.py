"""Home page with motto, circular action button, EQ ring, and live focus status."""

from __future__ import annotations

from math import cos, pi, sin

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from adaptive_soundscape.core.events import WorkContext

THEME_LABELS: dict[WorkContext, str] = {
    WorkContext.PROGRAMMING: "Coding",
    WorkContext.TEAM_WORKFLOW: "Collaborating",
    WorkContext.READING_WRITING: "Reading & Writing",
    WorkContext.SCIENTIFIC: "Research",
    WorkContext.CREATIVE_DESIGN: "Creating",
    WorkContext.DISTRACTION: "Distracted",
    WorkContext.UNKNOWN: "Neutral",
}

HOME_STYLE = """
QWidget#homePage {
    background-color: #1a1a1e;
}
QLabel#mottoLabel {
    color: #e8e8ec;
    font-size: 20px;
    font-weight: 700;
}
QLabel#themeLabel {
    color: #a0b8e8;
    font-size: 15px;
    font-weight: 700;
}
QLabel#focusPctLabel {
    color: #e8e8ec;
    font-size: 14px;
    font-weight: 700;
}
QLabel#focusTitleLabel {
    color: #c8c8d0;
    font-size: 13px;
    font-weight: 700;
}
QLabel#descriptionLabel {
    color: #7a7a86;
    font-size: 12px;
    font-weight: 700;
    line-height: 1.6;
}
QProgressBar#focusBar {
    background-color: #2e2e36;
    border: none;
    border-radius: 3px;
    height: 6px;
    max-width: 280px;
}
QProgressBar#focusBar::chunk {
    background-color: #5b8def;
    border-radius: 3px;
}
QFrame#descBox {
    background-color: #23232a;
    border: 1px solid #363640;
    border-radius: 10px;
    padding: 14px 18px;
}
"""

LIGHT_HOME_STYLE = """
QWidget#homePage {
    background-color: #f5f5f8;
}
QLabel#mottoLabel {
    color: #1a1a1e;
    font-size: 20px;
    font-weight: 700;
}
QLabel#themeLabel {
    color: #3d6fd4;
    font-size: 15px;
    font-weight: 700;
}
QLabel#focusPctLabel {
    color: #1a1a1e;
    font-size: 14px;
    font-weight: 700;
}
QLabel#focusTitleLabel {
    color: #505060;
    font-size: 13px;
    font-weight: 700;
}
QLabel#descriptionLabel {
    color: #686878;
    font-size: 12px;
    font-weight: 700;
    line-height: 1.6;
}
QProgressBar#focusBar {
    background-color: #d8d8e0;
    border: none;
    border-radius: 3px;
    height: 6px;
    max-width: 280px;
}
QProgressBar#focusBar::chunk {
    background-color: #5b8def;
    border-radius: 3px;
}
QFrame#descBox {
    background-color: #eaeaef;
    border: 1px solid #d0d0d8;
    border-radius: 10px;
    padding: 14px 18px;
}
"""

START_BUTTON_STYLE = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #7db5f8, stop:1 #4a7dd4);
    color: #ffffff;
    border: none;
    border-bottom: 4px solid #3560a0;
    border-radius: 75px;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 2px;
    padding: 0px 0px;
    text-align: center;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #8ec5ff, stop:1 #5b8def);
}
QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #4a7dd4, stop:1 #3560a0);
    border-bottom: 5px solid #254890;
}
"""

STOP_BUTTON_STYLE = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #e87070, stop:1 #b04040);
    color: #ffffff;
    border: none;
    border-bottom: 4px solid #802020;
    border-radius: 75px;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 2px;
    padding: 0px 0px;
    text-align: center;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #f09090, stop:1 #c05050);
}
QPushButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #b04040, stop:1 #802020);
    border-bottom: 5px solid #601010;
}
"""

DESCRIPTION_TEXT = (
    "Adaptive Cognitive Soundscape is an intelligent audio companion that\n"
    "monitors your workspace activity in real time — recognising whether you\n"
    "are coding, reading, designing, or distracted — and dynamically adjusts\n"
    "ambient background audio to sustain deep focus and reduce cognitive drift.\n"
    "It runs locally on your machine, works with your own sound libraries,\n"
    "and requires no internet connection."
)

DESC_BOX_STYLE = """
QFrame#descBox {
    background-color: #22222a;
    border: 1px solid #3a3a48;
    border-radius: 10px;
    padding: 14px 18px;
}
"""

LIGHT_DESC_BOX_STYLE = """
QFrame#descBox {
    background-color: #eaeaef;
    border: 1px solid #c8c8d0;
    border-radius: 10px;
    padding: 14px 18px;
}
"""


class EqRingWidget(QWidget):
    """Self-contained circular button that paints its own gradient background,
    label text, and 48 frequency bars in one paint pass.

    No QPushButton or z-order tricks needed — everything lives in this widget.
    """

    clicked = pyqtSignal()
    N_BARS = 48
    SMOOTH_ALPHA = 0.28

    # Geometry — circle is r=75, widget larger for the outward ring
    _RADIUS = 75
    _MAX_EXTENT = 38               # max pixels the curve extends beyond the button
    _N_CURVE = 720                 # high-res points for perfectly smooth curve

    # Gaussian neighbour‑spread
    _N_NEIGHBOUR = 3
    _SPREAD = [0.30, 0.20, 0.11, 0.04]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = "START"
        self._running = False
        self._hovered = False
        self._pressed = False
        self._active = False
        self._smooth: list[float] = [0.0] * self.N_BARS
        self._targets: list[float] = [0.0] * self.N_BARS
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # ── public API ──

    def start_ring(self, label: str = "STOP") -> None:
        self._running = True
        self._label = label
        self._active = True
        self._smooth = [0.0] * self.N_BARS
        self._timer.start(30)
        self.update()

    def stop_ring(self, label: str = "START") -> None:
        self._running = False
        self._label = label
        self._active = False
        self._timer.stop()
        self._smooth = [0.0] * self.N_BARS
        self.update()

    def set_bands(self, bands: list[float]) -> None:
        clamped = [max(0.0, min(1.0, v)) for v in bands]
        self._targets = clamped if len(clamped) == self.N_BARS else self._targets

    # ── events ──

    def _in_circle(self, pos) -> bool:
        """Check whether a point is inside the 75px-radius button circle."""
        cx, cy = self.width() / 2.0, self.height() / 2.0
        dx, dy = pos.x() - cx, pos.y() - cy
        return (dx * dx + dy * dy) <= self._RADIUS * self._RADIUS

    def enterEvent(self, event) -> None:  # noqa: N803
        if self._in_circle(event.position()):
            self._hovered = True
            self.update()

    def leaveEvent(self, _event) -> None:  # noqa: N803
        self._hovered = False
        self._pressed = False
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N803
        if self._in_circle(event.position()):
            if not self._hovered:
                self._hovered = True
                self.update()
        else:
            if self._hovered:
                self._hovered = False
                self._pressed = False
                self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N803
        if event.button() == Qt.MouseButton.LeftButton and self._in_circle(event.position()):
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N803
        if event.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self._in_circle(event.position()):
                self.clicked.emit()

    # ── tick + paint ──

    def _tick(self) -> None:
        a = self.SMOOTH_ALPHA
        n = self.N_BARS
        for i in range(n):
            self._smooth[i] += (self._targets[i] - self._smooth[i]) * a
        # Gaussian neighbour‑spread
        self._display: list[float] = [0.0] * n
        for i in range(n):
            acc = 0.0
            for d in range(self._N_NEIGHBOUR + 1):
                for sign in (+1, -1):
                    j = (i + sign * d) % n
                    acc += self._smooth[j] * self._SPREAD[d]
            self._display[i] = acc
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N803
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        r = self._RADIUS
        ext = self._MAX_EXTENT

        # ── 1. Continuous polar spectrogram ring ──
        if self._active:
            amps = getattr(self, '_display', self._smooth)
            n_bands = self.N_BARS
            n_curve = self._N_CURVE

            # Build smooth outer polygon — interpolate 48 bands → 360 points
            outer_pts: list[tuple[float, float]] = []
            for k in range(n_curve):
                angle = 2.0 * pi * k / n_curve
                # Fractional band index for this angle
                idx_frac = k / n_curve * n_bands
                i0 = int(idx_frac)
                frac = idx_frac - i0
                i1 = (i0 + 1) % n_bands
                amp = amps[i0] * (1.0 - frac) + amps[i1] * frac
                dist = r + amp * ext
                outer_pts.append((cx + dist * cos(angle), cy + dist * sin(angle)))

            # Inner circle (reversed) to close the ring.
            # Sink 2 px inside the button so the background circle drawn later
            # fully covers the inner seam — no anti-alias gap.
            inner_r = r - 2
            inner_pts: list[tuple[float, float]] = []
            for k in range(n_curve - 1, -1, -1):
                angle = 2.0 * pi * k / n_curve
                inner_pts.append((cx + inner_r * cos(angle), cy + inner_r * sin(angle)))

            ring_path = QPainterPath()
            ring_path.moveTo(*outer_pts[0])
            for pt in outer_pts[1:]:
                ring_path.lineTo(*pt)
            for pt in inner_pts:
                ring_path.lineTo(*pt)
            ring_path.closeSubpath()

            # Radial gradient fill — bright red at inner edge, fading outward
            grad = QRadialGradient(cx, cy, r + ext)
            grad.setColorAt(r / (r + ext), QColor(255, 60, 40, 200))
            grad.setColorAt((r + ext * 0.5) / (r + ext), QColor(255, 100, 60, 120))
            grad.setColorAt(1.0, QColor(255, 140, 80, 20))

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawPath(ring_path)

            # Bright outer contour line — closed loop
            outline_pen = QPen(QColor(255, 80, 50, 160), 1.5,
                               Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                               Qt.PenJoinStyle.RoundJoin)
            p.setPen(outline_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            # draw outer edge as a closed polygon
            out_path = QPainterPath()
            out_path.moveTo(*outer_pts[0])
            for pt in outer_pts[1:]:
                out_path.lineTo(*pt)
            out_path.closeSubpath()
            p.drawPath(out_path)

        # ── 2. Gradient background, clipped to circle ──
        p.save()
        clip_path = QPainterPath()
        clip_path.addEllipse(cx - r, cy - r, r * 2, r * 2)
        p.setClipPath(clip_path)

        bg = QPainterPath()
        bg.addEllipse(cx - r, cy - r, r * 2, r * 2)
        if self._running:
            top_c, bot_c = QColor(0xE8, 0x70, 0x70), QColor(0xB0, 0x40, 0x40)
            border_c = QColor(0x80, 0x20, 0x20)
            if self._hovered:
                top_c, bot_c = QColor(0xF0, 0x90, 0x90), QColor(0xC0, 0x50, 0x50)
            if self._pressed:
                top_c, bot_c = QColor(0xB0, 0x40, 0x40), QColor(0x80, 0x20, 0x20)
        else:
            top_c, bot_c = QColor(0x7D, 0xB5, 0xF8), QColor(0x4A, 0x7D, 0xD4)
            border_c = QColor(0x35, 0x60, 0xA0)
            if self._hovered:
                top_c, bot_c = QColor(0x8E, 0xC5, 0xFF), QColor(0x5B, 0x8D, 0xEF)
            if self._pressed:
                top_c, bot_c = QColor(0x4A, 0x7D, 0xD4), QColor(0x35, 0x60, 0xA0)

        lg = QLinearGradient(cx, cy - r, cx, cy + r)
        lg.setColorAt(0.0, top_c)
        lg.setColorAt(1.0, bot_c)
        p.fillPath(bg, lg)

        pen = QPen(border_c, 4)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))
        p.restore()

        # ── 3. Text label ──
        p.setPen(QColor(255, 255, 255))
        font = p.font()
        font.setPixelSize(20)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        p.setFont(font)
        p.drawText(int(cx - r), int(cy - r), int(r * 2), int(r * 2),
                   Qt.AlignmentFlag.AlignCenter, self._label)
        p.end()


class HomePage(QWidget):
    """Landing / dashboard page with start button and live focus status."""

    action_toggled = pyqtSignal(bool)  # True=start, False=stop

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("homePage")
        self.setStyleSheet(HOME_STYLE)
        self._running = False

        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(12)

        # ── Top area: QStackedWidget (motto ↔ focus bar + theme) ──
        self._top_stack = QStackedWidget()
        self._top_stack.setFixedHeight(80)

        # Page 0: Motto
        motto_w = QWidget()
        motto_l = QVBoxLayout(motto_w)
        motto_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._motto = QLabel("Your Focus, Amplified by Sound")
        self._motto.setObjectName("mottoLabel")
        self._motto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motto_l.addWidget(self._motto)
        self._top_stack.addWidget(motto_w)  # index 0

        # Page 1: Focus bar + theme label
        status_w = QWidget()
        status_l = QVBoxLayout(status_w)
        status_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_l.setSpacing(8)

        focus_row = QHBoxLayout()
        focus_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        focus_title = QLabel("FOCUS")
        focus_title.setObjectName("focusTitleLabel")
        self._focus_bar = QProgressBar()
        self._focus_bar.setObjectName("focusBar")
        self._focus_bar.setRange(0, 100)
        self._focus_bar.setTextVisible(False)
        self._focus_bar.setFixedWidth(240)
        self._focus_pct = QLabel("0%")
        self._focus_pct.setObjectName("focusPctLabel")
        focus_row.addWidget(focus_title)
        focus_row.addSpacing(8)
        focus_row.addWidget(self._focus_bar)
        focus_row.addSpacing(8)
        focus_row.addWidget(self._focus_pct)
        status_l.addLayout(focus_row)

        self._theme_label = QLabel("")
        self._theme_label.setObjectName("themeLabel")
        self._theme_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_l.addWidget(self._theme_label)

        self._top_stack.addWidget(status_w)  # index 1

        root.addWidget(self._top_stack, alignment=Qt.AlignmentFlag.AlignCenter)

        # ── Center: circular button with outward EQ bars (needs extra canvas) ──
        BTN_SZ = 220  # larger than the 150px circle to give bars room
        self._eq_ring = EqRingWidget()
        self._eq_ring.setFixedSize(BTN_SZ, BTN_SZ)
        self._eq_ring.clicked.connect(self._on_action)

        btn_container = QHBoxLayout()
        btn_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_container.addWidget(self._eq_ring)
        root.addLayout(btn_container)

        # ── Bottom: full product description, boxed, left-aligned ──
        self._desc_box = QFrame()
        self._desc_box.setObjectName("descBox")
        self._desc_box.setMaximumWidth(520)
        desc_inner = QVBoxLayout(self._desc_box)
        desc_inner.setContentsMargins(0, 0, 0, 0)

        self._description = QLabel(DESCRIPTION_TEXT)
        self._description.setObjectName("descriptionLabel")
        self._description.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._description.setWordWrap(True)
        desc_inner.addWidget(self._description)

        desc_container = QHBoxLayout()
        desc_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_container.addWidget(self._desc_box)
        root.addLayout(desc_container)

        root.addStretch()

    # ── Slots / Public API ──────────────────────────────────────

    def _on_action(self) -> None:
        """User clicked the action button — emit intent to toggle."""
        self.action_toggled.emit(not self._running)

    def set_running(self, running: bool) -> None:
        """Sync button text, colour, and top-area content from the app."""
        if self._running == running:
            return
        self._running = running
        if running:
            self._eq_ring.start_ring("STOP")
            self._top_stack.setCurrentIndex(1)
        else:
            self._eq_ring.stop_ring("START")
            self._top_stack.setCurrentIndex(0)

    def set_frequency_bands(self, bands: list[float]) -> None:
        """Forward real-time frequency-band amplitudes to the EQ ring."""
        self._eq_ring.set_bands(bands)

    def update_status(self, *, context: WorkContext, focus_score: float) -> None:
        """Refresh focus bar and theme label (called ~1 Hz while running)."""
        if not self._running:
            return

        pct = int(max(0.0, min(1.0, focus_score)) * 100)
        self._focus_bar.setValue(pct)
        self._focus_pct.setText(f"{pct}%")

        theme = THEME_LABELS.get(context, "Neutral")
        if pct >= 80:
            mood = "Deep Focus"
        elif pct >= 60:
            mood = "In the Zone"
        elif pct >= 40:
            mood = "Light Focus"
        elif pct >= 20:
            mood = "Wandering"
        else:
            mood = "Distracted"

        self._theme_label.setText(f"{theme}  ·  {mood}")

    # ------------------------------------------------------------------
    # Theme switching
    # ------------------------------------------------------------------

    def set_dark_mode(self, enabled: bool) -> None:
        """Apply dark / light stylesheet on the home page."""
        self._dark = enabled
        self.setStyleSheet(HOME_STYLE if enabled else LIGHT_HOME_STYLE)
        self._desc_box.setStyleSheet(DESC_BOX_STYLE if enabled else LIGHT_DESC_BOX_STYLE)

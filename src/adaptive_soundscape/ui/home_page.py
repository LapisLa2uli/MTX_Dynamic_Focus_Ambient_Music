"""Home page with motto, circular action button, EQ ring, and live focus status."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin
from random import Random

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
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
from adaptive_soundscape.ui.settings_page import DEFAULT_STATUS_COLORS

THEME_LABELS: dict[WorkContext, str] = {
    WorkContext.PROGRAMMING: "Coding",
    WorkContext.TEAM_WORKFLOW: "Collaborating",
    WorkContext.READING_WRITING: "Reading & Writing",
    WorkContext.SCIENTIFIC: "Research",
    WorkContext.CREATIVE_DESIGN: "Creating",
    WorkContext.DISTRACTION: "Distracted",
    WorkContext.UNKNOWN: "Neutral",
}

def _home_stylesheet(*, dark: bool, scale: float = 1.0) -> str:
    """Home-page QSS with fonts/metrics scaled for the current window size."""

    def px(n: float, minimum: int = 1) -> str:
        return f"{max(minimum, int(round(n * scale)))}px"

    if dark:
        return f"""
QWidget#homePage {{
    background: transparent;
}}
QLabel#mottoLabel {{
    color: #e8e8ec;
    font-size: {px(20, 14)};
    font-weight: 700;
}}
QLabel#themeLabel {{
    color: #a0b8e8;
    font-size: {px(15, 12)};
    font-weight: 700;
}}
QLabel#focusPctLabel {{
    color: #e8e8ec;
    font-size: {px(14, 11)};
    font-weight: 700;
}}
QLabel#focusTitleLabel {{
    color: #c8c8d0;
    font-size: {px(13, 10)};
    font-weight: 700;
}}
QLabel#descriptionLabel {{
    color: #7a7a86;
    font-size: {px(12, 10)};
    font-weight: 700;
    line-height: 1.6;
}}
QProgressBar#focusBar {{
    background-color: #2e2e36;
    border: none;
    border-radius: {px(3)};
    height: {px(6, 4)};
    max-width: {px(280, 160)};
}}
QProgressBar#focusBar::chunk {{
    background-color: #5b8def;
    border-radius: {px(3)};
}}
QFrame#descBox {{
    background-color: #23232a;
    border: 1px solid #363640;
    border-radius: {px(10, 6)};
    padding: {px(14, 8)} {px(18, 10)};
}}
"""
    return f"""
QWidget#homePage {{
    background: transparent;
}}
QLabel#mottoLabel {{
    color: #1a1a1e;
    font-size: {px(20, 14)};
    font-weight: 700;
}}
QLabel#themeLabel {{
    color: #3d6fd4;
    font-size: {px(15, 12)};
    font-weight: 700;
}}
QLabel#focusPctLabel {{
    color: #1a1a1e;
    font-size: {px(14, 11)};
    font-weight: 700;
}}
QLabel#focusTitleLabel {{
    color: #505060;
    font-size: {px(13, 10)};
    font-weight: 700;
}}
QLabel#descriptionLabel {{
    color: #686878;
    font-size: {px(12, 10)};
    font-weight: 700;
    line-height: 1.6;
}}
QProgressBar#focusBar {{
    background-color: #d8d8e0;
    border: none;
    border-radius: {px(3)};
    height: {px(6, 4)};
    max-width: {px(280, 160)};
}}
QProgressBar#focusBar::chunk {{
    background-color: #5b8def;
    border-radius: {px(3)};
}}
QFrame#descBox {{
    background-color: #eaeaef;
    border: 1px solid #d0d0d8;
    border-radius: {px(10, 6)};
    padding: {px(14, 8)} {px(18, 10)};
}}
"""


# Back-compat aliases (scale 1.0)
HOME_STYLE = _home_stylesheet(dark=True, scale=1.0)
LIGHT_HOME_STYLE = _home_stylesheet(dark=False, scale=1.0)

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


@dataclass
class _AuroraBlob:
    """Normalized floating blob for the home aurora background."""

    x: float
    y: float
    vx: float
    vy: float
    radius: float
    phase: float
    speed: float
    hue_shift: float
    sat_scale: float
    alpha: int


class EqRingWidget(QWidget):
    """Self-contained circular button that paints its own gradient background,
    label text, and a spectrogram ring in one paint pass.

    No QPushButton or z-order tricks needed — everything lives in this widget.
    Geometry scales with the widget size (design reference: 220×220 → r=75).
    """

    clicked = pyqtSignal()
    N_BARS = 48
    DEFAULT_SMOOTHNESS = 0.35
    _TICK_MS = 16  # ≈60 Hz
    _DESIGN_SIZE = 220.0
    _DESIGN_RADIUS = 75.0
    _DESIGN_EXTENT = 38.0
    _N_CURVE = 720                 # high-res points for a smooth closed path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = "START"
        self._running = False
        self._hovered = False
        self._pressed = False
        self._active = False
        self._ambient = QColor(180, 190, 210)
        self._smooth: list[float] = [0.0] * self.N_BARS
        self._targets: list[float] = [0.0] * self.N_BARS
        self._display: list[float] = [0.0] * self.N_BARS
        self._smoothness = self.DEFAULT_SMOOTHNESS
        self._apply_smoothness_params(self._smoothness)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

    def set_ambient_tint(self, color: QColor) -> None:
        """Tint the frosted glass from the aurora colour behind the button."""
        if not color.isValid():
            return
        if (
            color.red() == self._ambient.red()
            and color.green() == self._ambient.green()
            and color.blue() == self._ambient.blue()
        ):
            return
        self._ambient = QColor(color)
        self.update()

    def _geom(self) -> tuple[float, float, float, float]:
        """Return (cx, cy, radius, ring_extent) from current widget size."""
        w, h = float(self.width()), float(self.height())
        size = min(w, h)
        scale = size / self._DESIGN_SIZE
        r = self._DESIGN_RADIUS * scale
        ext = self._DESIGN_EXTENT * scale
        return w / 2.0, h / 2.0, r, ext

    # ── public API ──

    def start_ring(self, label: str = "STOP") -> None:
        self._running = True
        self._label = label
        self._active = True
        self._smooth = [0.0] * self.N_BARS
        self._display = [0.0] * self.N_BARS
        self._timer.start(self._TICK_MS)
        self.update()

    def stop_ring(self, label: str = "START") -> None:
        self._running = False
        self._label = label
        self._active = False
        self._timer.stop()
        self._smooth = [0.0] * self.N_BARS
        self._display = [0.0] * self.N_BARS
        self.update()

    def set_bands(self, bands: list[float]) -> None:
        clamped = [max(0.0, min(1.0, v)) for v in bands]
        self._targets = clamped if len(clamped) == self.N_BARS else self._targets

    def set_smoothness(self, value: float) -> None:
        """0 = detailed / spiky waveform; 1 = very soft oval-like lobes."""
        self._smoothness = max(0.0, min(1.0, float(value)))
        self._apply_smoothness_params(self._smoothness)

    def _apply_smoothness_params(self, s: float) -> None:
        # Temporal ease: snappier when detailed, laggy when soft.
        self._smooth_alpha = 0.34 - s * 0.24
        # Circular blur width
        self._n_neighbour = max(1, int(round(1 + s * 6)))
        # Harmonic cut-off: many modes (detailed) → few modes (oval)
        self._keep_modes = max(3, int(round(20 - s * 16)))
        self._harmonic_mix = s  # blend toward harmonic projection
        self._floor = 0.03 + s * 0.07
        # Cosine interpolation amount in paint (0=linear, 1=full cosine)
        self._interp_cosine = s
        # Precompute a decaying neighbour kernel for current width
        weights = [1.0]
        for d in range(1, self._n_neighbour + 1):
            weights.append(0.55 ** d)
        total = weights[0] + 2.0 * sum(weights[1:])
        self._spread = [w / total for w in weights]

    # ── events ──

    def _in_circle(self, pos) -> bool:
        """Check whether a point is inside the button circle."""
        cx, cy, r, _ext = self._geom()
        dx, dy = pos.x() - cx, pos.y() - cy
        return (dx * dx + dy * dy) <= r * r

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

    @staticmethod
    def _circular_harmonic_lowpass(values: list[float], keep_modes: int) -> list[float]:
        """Project ring samples onto a short Fourier series (sum of sines/cosines)."""
        n = len(values)
        if n == 0:
            return values
        mean = sum(values) / n
        recon = [mean] * n
        modes = min(keep_modes, n // 2)
        for k in range(1, modes + 1):
            ck = 0.0
            sk = 0.0
            for idx, x in enumerate(values):
                ang = 2.0 * pi * k * idx / n
                ck += x * cos(ang)
                sk += x * sin(ang)
            ck *= 2.0 / n
            sk *= 2.0 / n
            for idx in range(n):
                ang = 2.0 * pi * k * idx / n
                recon[idx] += ck * cos(ang) + sk * sin(ang)
        return [max(0.0, v) for v in recon]

    def _tick(self) -> None:
        a = self._smooth_alpha
        n = self.N_BARS
        for i in range(n):
            self._smooth[i] += (self._targets[i] - self._smooth[i]) * a

        # Circular blur (width depends on smoothness)
        blurred = [0.0] * n
        for i in range(n):
            acc = self._smooth[i] * self._spread[0]
            for d in range(1, self._n_neighbour + 1):
                w = self._spread[d]
                acc += self._smooth[(i + d) % n] * w
                acc += self._smooth[(i - d) % n] * w
            blurred[i] = acc

        def _norm(vals: list[float]) -> list[float]:
            mx = max(vals) if vals else 0.0
            if mx <= 1e-6:
                return [0.0] * len(vals)
            return [min(1.0, v / mx) for v in vals]

        detailed = _norm(blurred)
        mix = self._harmonic_mix
        if mix < 0.02:
            shaped = detailed
        else:
            harmonic = _norm(
                self._circular_harmonic_lowpass(blurred, self._keep_modes)
            )
            shaped = [
                (1.0 - mix) * d + mix * h for d, h in zip(detailed, harmonic)
            ]
            shaped = _norm(shaped)

        floor = self._floor
        self._display = [floor + (1.0 - floor) * v for v in shaped]
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N803
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r, ext = self._geom()
        scale = r / self._DESIGN_RADIUS if self._DESIGN_RADIUS else 1.0

        # ── 1. Continuous polar spectrogram ring ──
        if self._active:
            amps = self._display
            n_bands = self.N_BARS
            n_curve = self._N_CURVE

            # Cosine-interpolated sampling around the ring → C1-smooth outline
            outer_pts: list[tuple[float, float]] = []
            for k in range(n_curve):
                angle = 2.0 * pi * k / n_curve
                idx_frac = k / n_curve * n_bands
                i0 = int(idx_frac) % n_bands
                frac = idx_frac - int(idx_frac)
                i1 = (i0 + 1) % n_bands
                # Blend linear ↔ cosine interpolation from smoothness setting
                t_cos = 0.5 - 0.5 * cos(pi * frac)
                t = (1.0 - self._interp_cosine) * frac + self._interp_cosine * t_cos
                amp = amps[i0] * (1.0 - t) + amps[i1] * t
                dist = r + amp * ext
                outer_pts.append((cx + dist * cos(angle), cy + dist * sin(angle)))

            # Inner circle (reversed) to close the ring.
            # Sink 2 px inside the button so the background circle drawn later
            # fully covers the inner seam — no anti-alias gap.
            inner_r = r - 2 * scale
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

            # Radial gradient fill — theme colour (eases with work-type aurora)
            theme = self._ambient
            h, s, v, _a = theme.getHsvF()
            if h < 0:
                h = 0.0
            s = min(1.0, max(0.35, s * 1.15 + 0.1))
            v = min(1.0, max(0.55, v * 1.1 + 0.08))

            def _tint(sat: float, val: float, alpha: int) -> QColor:
                c = QColor()
                c.setHsvF(h, min(1.0, sat), min(1.0, val), 1.0)
                c.setAlpha(alpha)
                return c

            grad = QRadialGradient(cx, cy, r + ext)
            grad.setColorAt(r / (r + ext), _tint(s, v, 200))
            grad.setColorAt((r + ext * 0.5) / (r + ext), _tint(s * 0.85, v * 0.95, 120))
            grad.setColorAt(1.0, _tint(s * 0.55, v * 0.85, 20))

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawPath(ring_path)

            # Bright outer contour line — closed loop
            outline_pen = QPen(
                _tint(s, min(1.0, v * 1.05), 165),
                max(1.0, 1.5 * scale),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
            p.setPen(outline_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            # draw outer edge as a closed polygon
            out_path = QPainterPath()
            out_path.moveTo(*outer_pts[0])
            for pt in outer_pts[1:]:
                out_path.lineTo(*pt)
            out_path.closeSubpath()
            p.drawPath(out_path)

        # ── 2. Translucent liquid-glass disc ──
        self._paint_liquid_glass(p, cx, cy, r, scale)

        # ── 3. Text label (soft shadow so it stays readable on glass) ──
        font = p.font()
        font.setPixelSize(max(12, int(round(20 * scale))))
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(1.0, 2 * scale))
        p.setFont(font)
        text_rect_x, text_rect_y = int(cx - r), int(cy - r)
        text_rect_w, text_rect_h = int(r * 2), int(r * 2)
        p.setPen(QColor(0, 0, 0, 90))
        p.drawText(
            text_rect_x,
            text_rect_y + max(1, int(round(scale))),
            text_rect_w,
            text_rect_h,
            Qt.AlignmentFlag.AlignCenter,
            self._label,
        )
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(
            text_rect_x,
            text_rect_y,
            text_rect_w,
            text_rect_h,
            Qt.AlignmentFlag.AlignCenter,
            self._label,
        )
        p.end()

    def _paint_liquid_glass(
        self, p: QPainter, cx: float, cy: float, r: float, scale: float = 1.0
    ) -> None:
        """Flat translucent glass pane — frosted disk, not a spherical orb."""
        amb = self._ambient
        hover = self._hovered and not self._pressed
        press = self._pressed
        shine_a = 14 if hover else 0
        press_dim = 10 if press else 0

        body = QPainterPath()
        body.addEllipse(cx - r, cy - r, r * 2, r * 2)

        # Soft ambient bloom around the rim (flat pane catch-light, not a lens orb)
        bloom_r = r * 1.18
        bloom = QRadialGradient(cx, cy, bloom_r)
        bloom_a = max(0, 28 + shine_a // 2 - press_dim)
        bloom.setColorAt(0.72, QColor(amb.red(), amb.green(), amb.blue(), 0))
        bloom.setColorAt(0.9, QColor(amb.red(), amb.green(), amb.blue(), bloom_a))
        bloom.setColorAt(1.0, QColor(amb.red(), amb.green(), amb.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bloom)
        p.drawEllipse(QRectF(cx - bloom_r, cy - bloom_r, bloom_r * 2, bloom_r * 2))

        p.save()
        p.setClipPath(body)

        # Even frost plate — mostly uniform so it reads as a pane, not a bulb
        frost = QLinearGradient(cx, cy - r, cx, cy + r)
        frost.setColorAt(0.0, QColor(255, 255, 255, 58 + shine_a))
        frost.setColorAt(0.35, QColor(235, 238, 245, 32 + shine_a // 2))
        frost.setColorAt(0.7, QColor(210, 216, 228, 36 + press_dim // 2))
        frost.setColorAt(1.0, QColor(190, 198, 210, 44 + press_dim))
        p.fillPath(body, frost)

        # Ambient tint wash (flat overlay)
        amb_a = max(0, 36 + shine_a // 2 - press_dim)
        p.fillPath(
            body,
            QColor(amb.red(), amb.green(), amb.blue(), amb_a),
        )

        # Subtle start/stop cue
        if self._running:
            p.fillPath(body, QColor(255, 120, 100, 18 + press_dim // 2))
        else:
            p.fillPath(body, QColor(140, 190, 255, 14 + press_dim // 2))

        # Thin top-edge specular band (glass pane highlight, not a sphere sheen)
        band = QPainterPath()
        band.addEllipse(cx - r, cy - r, r * 2, r * 2)
        band_clip = QPainterPath()
        band_clip.addRect(cx - r, cy - r, r * 2, r * 0.42)
        band = band.intersected(band_clip)
        band_grad = QLinearGradient(cx, cy - r, cx, cy - r * 0.15)
        top_a = 95 if hover else 70
        band_grad.setColorAt(0.0, QColor(255, 255, 255, top_a))
        band_grad.setColorAt(0.55, QColor(255, 255, 255, 28))
        band_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(band, band_grad)

        # Soft inner edge darkening — shallow, keeps the pane flat
        edge = QRadialGradient(cx, cy, r)
        edge.setColorAt(0.0, QColor(0, 0, 0, 0))
        edge.setColorAt(0.82, QColor(0, 0, 0, 0))
        edge.setColorAt(1.0, QColor(12, 14, 20, 28 + press_dim))
        p.fillPath(body, edge)

        p.restore()

        # Thin bright rim — glass edge, not a soft spherical halo
        rim_light = QColor(255, 255, 255, 130 if hover else 105)
        rim_pen = QPen(rim_light, max(1.0, 1.4 * scale))
        p.setPen(rim_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        inset = 0.6 * scale
        p.drawEllipse(
            QRectF(cx - r + inset, cy - r + inset, (r - inset) * 2, (r - inset) * 2)
        )

        rim_outer = QColor(amb.red(), amb.green(), amb.blue(), 55)
        outer_pen = QPen(rim_outer, max(1.0, 1.2 * scale))
        p.setPen(outer_pen)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))


class HomePage(QWidget):
    """Landing / dashboard page with start button and live focus status."""

    action_toggled = pyqtSignal(bool)  # True=start, False=stop

    # Design reference for responsive layout (content area ~590×520 at min window)
    _REF_W = 590.0
    _REF_H = 520.0
    _BTN_DESIGN = 220
    _BLOB_MIN = 4
    _BLOB_MAX = 14

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("homePage")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._running = False
        self._dark = True
        self._layout_scale = 1.0
        self._aurora_color = QColor(DEFAULT_STATUS_COLORS["unknown"])
        self._aurora_target = QColor(self._aurora_color)
        self._focus_level = 0.0
        self._focus_target = 0.0
        self._aurora_brightness_gain = 1.5
        self._blob_count_f = float(self._BLOB_MIN)
        self._blob_rng = Random(7)
        self._blobs = self._make_blobs(self._BLOB_MAX, seed=7)
        self._aurora_timer = QTimer(self)
        self._aurora_timer.timeout.connect(self._tick_aurora)
        self._aurora_timer.start(33)  # ~30 fps drift — soft screensaver pace

        self._root = QVBoxLayout(self)
        self._root.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root.setContentsMargins(32, 32, 32, 32)
        self._root.setSpacing(12)

        self._root.addStretch(1)

        # ── Top area: QStackedWidget (motto ↔ focus bar + theme) ──
        self._top_stack = QStackedWidget()
        self._top_stack.setFixedHeight(80)
        self._top_stack.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._top_stack.setStyleSheet("background: transparent;")

        # Page 0: Motto
        motto_w = QWidget()
        motto_w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        motto_w.setStyleSheet("background: transparent;")
        motto_l = QVBoxLayout(motto_w)
        motto_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._motto = QLabel("Your Focus, Amplified by Sound")
        self._motto.setObjectName("mottoLabel")
        self._motto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motto_l.addWidget(self._motto)
        self._top_stack.addWidget(motto_w)  # index 0

        # Page 1: Focus bar + theme label
        status_w = QWidget()
        status_w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        status_w.setStyleSheet("background: transparent;")
        self._status_layout = QVBoxLayout(status_w)
        self._status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_layout.setSpacing(8)

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
        self._status_layout.addLayout(focus_row)

        self._theme_label = QLabel("")
        self._theme_label.setObjectName("themeLabel")
        self._theme_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_layout.addWidget(self._theme_label)

        self._music_detail = QLabel("")
        self._music_detail.setObjectName("descriptionLabel")
        self._music_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._music_detail.setWordWrap(True)
        self._status_layout.addWidget(self._music_detail)

        self._top_stack.addWidget(status_w)  # index 1

        self._root.addWidget(self._top_stack, alignment=Qt.AlignmentFlag.AlignCenter)

        # ── Center: circular button with outward EQ bars (needs extra canvas) ──
        self._eq_ring = EqRingWidget()
        self._eq_ring.setFixedSize(self._BTN_DESIGN, self._BTN_DESIGN)
        self._eq_ring.clicked.connect(self._on_action)

        btn_container = QHBoxLayout()
        btn_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_container.addWidget(self._eq_ring)
        self._root.addLayout(btn_container)

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
        self._root.addLayout(desc_container)

        self._root.addStretch(1)

        self.setStyleSheet(_home_stylesheet(dark=True, scale=1.0))
        self._desc_box.setStyleSheet(DESC_BOX_STYLE)
        self._apply_layout_scale(force=True)

    def resizeEvent(self, event) -> None:  # noqa: N803
        super().resizeEvent(event)
        self._apply_layout_scale()

    def _compute_layout_scale(self) -> float:
        w = max(float(self.width()), 1.0)
        h = max(float(self.height()), 1.0)
        raw = min(w / self._REF_W, h / self._REF_H)
        # Keep readable at small sizes; grow on fullscreen / large monitors
        return max(0.88, min(2.4, raw))

    def _apply_layout_scale(self, *, force: bool = False) -> None:
        scale = self._compute_layout_scale()
        if not force and abs(scale - self._layout_scale) < 0.02:
            return
        self._layout_scale = scale

        m = max(16, int(round(32 * scale)))
        self._root.setContentsMargins(m, m, m, m)
        self._root.setSpacing(max(8, int(round(12 * scale))))
        self._status_layout.setSpacing(max(4, int(round(8 * scale))))

        top_h = max(64, int(round(80 * scale)))
        # Running status can wrap music detail — give a bit more room when scaled up
        if self._running:
            top_h = max(top_h, int(round(110 * scale)))
        self._top_stack.setFixedHeight(top_h)

        btn = max(160, int(round(self._BTN_DESIGN * scale)))
        self._eq_ring.setFixedSize(btn, btn)

        self._focus_bar.setFixedWidth(max(160, int(round(240 * scale))))
        desc_w = min(max(280, int(round(520 * scale))), max(280, self.width() - 2 * m))
        self._desc_box.setMaximumWidth(desc_w)

        self.setStyleSheet(_home_stylesheet(dark=self._dark, scale=scale))
        # Desc box has its own stylesheet for theme; keep border padding in sync via object stylesheet
        self._desc_box.setStyleSheet(
            DESC_BOX_STYLE if self._dark else LIGHT_DESC_BOX_STYLE
        )
        self._eq_ring.update()
    # ── Aurora background ───────────────────────────────────────

    @staticmethod
    def _make_blobs(count: int, seed: int = 7) -> list[_AuroraBlob]:
        rng = Random(seed)
        blobs: list[_AuroraBlob] = []
        for _ in range(count):
            blobs.append(
                _AuroraBlob(
                    x=rng.uniform(0.1, 0.9),
                    y=rng.uniform(0.1, 0.9),
                    vx=rng.uniform(-0.012, 0.012),
                    vy=rng.uniform(-0.010, 0.010),
                    radius=rng.uniform(0.22, 0.48),
                    phase=rng.uniform(0.0, 2.0 * pi),
                    speed=rng.uniform(0.25, 0.55),
                    hue_shift=rng.uniform(-18.0, 18.0),
                    sat_scale=rng.uniform(0.55, 0.95),
                    alpha=rng.randint(28, 52),
                )
            )
        return blobs

    def _target_blob_count(self) -> float:
        """Focus raises how many flowing orbs are present (min → max)."""
        span = float(self._BLOB_MAX - self._BLOB_MIN)
        return self._BLOB_MIN + self._focus_level * span

    def set_aurora_color(self, hex_color: str) -> None:
        """Retarget aurora blobs to the active task / status colour (soft ease)."""
        c = QColor(hex_color)
        if not c.isValid():
            return
        self._aurora_target = c

    def set_aurora_brightness_gain(self, value: float) -> None:
        """How strongly focus brightens the flowing lights (0–3)."""
        self._aurora_brightness_gain = max(0.0, min(3.0, float(value)))
        self.update()

    def _aurora_brightness(self) -> float:
        """Multiplier applied to blob / wash alphas from focus × gain."""
        return 1.0 + self._focus_level * self._aurora_brightness_gain

    def _tick_aurora(self) -> None:
        # Ease theme colour (fast enough to feel responsive on context change)
        cur, tgt = self._aurora_color, self._aurora_target
        self._aurora_color = QColor(
            int(cur.red() + (tgt.red() - cur.red()) * 0.12),
            int(cur.green() + (tgt.green() - cur.green()) * 0.12),
            int(cur.blue() + (tgt.blue() - cur.blue()) * 0.12),
        )
        # Ease focus-driven brightness + orb count
        idle_target = self._focus_target if self._running else 0.0
        self._focus_level += (idle_target - self._focus_level) * 0.1
        count_target = self._target_blob_count()
        prev_count = self._blob_count_f
        self._blob_count_f += (count_target - self._blob_count_f) * 0.08
        # Respawn newly appearing orbs so they fade in from fresh positions
        for i, blob in enumerate(self._blobs):
            if self._blob_count_f > i >= prev_count:
                blob.x = self._blob_rng.uniform(0.08, 0.92)
                blob.y = self._blob_rng.uniform(0.08, 0.92)
                blob.phase = self._blob_rng.uniform(0.0, 2.0 * pi)

        self._eq_ring.set_ambient_tint(self._aurora_color)

        dt = 0.033
        visible_ceil = min(len(self._blobs), int(self._blob_count_f) + 1)
        for blob in self._blobs[:visible_ceil]:
            blob.phase += blob.speed * dt
            # Soft horizontal drift + vertical sine sway (aurora curtains)
            blob.x += blob.vx * dt * 8.0
            blob.y += blob.vy * dt * 8.0 + 0.004 * sin(blob.phase)
            if blob.x < -0.15 or blob.x > 1.15:
                blob.vx *= -1.0
                blob.x = max(-0.15, min(1.15, blob.x))
            if blob.y < -0.15 or blob.y > 1.15:
                blob.vy *= -1.0
                blob.y = max(-0.15, min(1.15, blob.y))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N803
        """Paint dim base + faint floating colour blobs (screensaver / aurora)."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = max(self.width(), 1), max(self.height(), 1)
        bright = self._aurora_brightness()

        if self._dark:
            base = QColor(0x1A, 0x1A, 0x1E)
        else:
            base = QColor(0xF5, 0xF5, 0xF8)
        p.fillRect(self.rect(), base)

        def _scaled_alpha(a: int) -> int:
            return int(min(255, max(0, round(a * bright))))

        # Subtle vertical wash so blobs feel layered in depth
        wash = QLinearGradient(0, 0, 0, h)
        theme = QColor(self._aurora_color)
        if self._dark:
            wash.setColorAt(0.0, QColor(theme.red(), theme.green(), theme.blue(), _scaled_alpha(22)))
            wash.setColorAt(0.55, QColor(theme.red(), theme.green(), theme.blue(), _scaled_alpha(8)))
            wash.setColorAt(1.0, QColor(0, 0, 0, 40))
        else:
            wash.setColorAt(0.0, QColor(theme.red(), theme.green(), theme.blue(), _scaled_alpha(28)))
            wash.setColorAt(0.6, QColor(theme.red(), theme.green(), theme.blue(), _scaled_alpha(10)))
            wash.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(self.rect(), wash)

        scale = float(min(w, h))
        for i, blob in enumerate(self._blobs):
            # Soft per-orb fade as focus raises / lowers the count
            presence = max(0.0, min(1.0, self._blob_count_f - i))
            if presence <= 0.01:
                continue

            pulse = 0.85 + 0.15 * sin(blob.phase)
            rad = blob.radius * scale * pulse
            cx = blob.x * w
            cy = blob.y * h

            c = QColor(self._aurora_color)
            h_deg, s, v, _a = c.getHsvF()
            if h_deg < 0:
                h_deg = 0.0
            h_deg = (h_deg + blob.hue_shift / 360.0) % 1.0
            s = min(1.0, max(0.0, s * blob.sat_scale + (0.15 if self._dark else 0.05)))
            # Focus lifts luminance of the flowing lights
            v_boost = 1.0 + 0.35 * self._focus_level * self._aurora_brightness_gain
            v = min(1.0, v * (1.05 if self._dark else 0.92) * v_boost)
            c.setHsvF(h_deg, s, v)

            alpha = blob.alpha if self._dark else int(blob.alpha * 0.55)
            breath = 0.75 + 0.25 * sin(blob.phase * 0.7)
            alpha = _scaled_alpha(int(alpha * breath * presence))

            grad = QRadialGradient(cx, cy, rad)
            grad.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), alpha))
            grad.setColorAt(0.35, QColor(c.red(), c.green(), c.blue(), int(alpha * 0.45)))
            grad.setColorAt(0.7, QColor(c.red(), c.green(), c.blue(), int(alpha * 0.12)))
            grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawEllipse(
                int(cx - rad),
                int(cy - rad),
                int(rad * 2),
                int(rad * 2),
            )
        p.end()

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
        self._apply_layout_scale(force=True)

    def set_frequency_bands(self, bands: list[float]) -> None:
        """Forward real-time frequency-band amplitudes to the EQ ring."""
        self._eq_ring.set_bands(bands)

    def set_waveform_smoothness(self, value: float) -> None:
        """Forward Settings slider (0–1) to the EQ ring."""
        self._eq_ring.set_smoothness(value)

    def update_status(
        self,
        *,
        context: WorkContext,
        focus_score: float,
        music_state: str = "",
        music_detail: str = "",
        theme_color: str = "",
    ) -> None:
        """Refresh focus UI (while running) and always retint the aurora."""
        color = theme_color or DEFAULT_STATUS_COLORS.get(
            context.value, DEFAULT_STATUS_COLORS["unknown"]
        )
        self.set_aurora_color(color)
        self._focus_target = max(0.0, min(1.0, float(focus_score)))

        if not self._running:
            return

        pct = int(max(0.0, min(1.0, focus_score)) * 100)
        self._focus_bar.setValue(pct)
        self._focus_pct.setText(f"{pct}%")

        theme = THEME_LABELS.get(context, "Neutral")
        if music_state:
            mood = music_state
        elif pct >= 80:
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
        self._music_detail.setText(music_detail)
        self._music_detail.setVisible(bool(music_detail))

    # ------------------------------------------------------------------
    # Theme switching
    # ------------------------------------------------------------------

    def set_dark_mode(self, enabled: bool) -> None:
        """Apply dark / light stylesheet on the home page."""
        self._dark = enabled
        self._apply_layout_scale(force=True)
        self.update()

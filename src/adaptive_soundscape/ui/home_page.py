"""Home page with motto, circular action button, EQ ring, and live focus status."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin
from random import Random

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from adaptive_soundscape.core.events import WorkContext
from adaptive_soundscape.core.i18n import (
    set_language as i18n_set_language,
    theme_label as i18n_theme_label,
    tr,
)
from adaptive_soundscape.ui.settings_page import DEFAULT_STATUS_COLORS

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
    color: #ffffff;
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
QPushButton#classifyBtn {{
    background-color: #2a2a36;
    border: 2px solid #555566;
    border-radius: {px(14, 8)};
    padding: {px(6, 4)} {px(14, 10)};
    color: #b0b0be;
    font-size: {px(11, 9)};
    font-weight: 600;
}}
QPushButton#pomoBtn, QPushButton#calibBtn {{
    background-color: #2a2a36;
    border: 2px solid #555566;
    border-radius: {px(18, 12)};
    min-height: {px(36, 24)};
    padding: {px(6, 4)} {px(14, 10)};
    color: #b0b0be;
    font-size: {px(11, 8)};
    font-weight: 600;
}}
QPushButton#classifyBtn:hover, QPushButton#pomoBtn:hover, QPushButton#calibBtn:hover {{
    border-color: #5b8def;
    color: #ccd8f8;
    background-color: rgba(91, 141, 239, 0.16);
}}
QPushButton#pomoBtn[active="true"], QPushButton#calibBtn[active="true"] {{
    border-color: #5b8def;
    border-radius: {px(18, 12)};
    min-height: {px(36, 24)};
    color: #e8eefc;
    background-color: rgba(91, 141, 239, 0.22);
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
    color: #000000;
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
QPushButton#classifyBtn {{
    background-color: #eaeaef;
    border: 2px solid #c0c0cc;
    border-radius: {px(14, 8)};
    padding: {px(6, 4)} {px(14, 10)};
    color: #686878;
    font-size: {px(11, 9)};
    font-weight: 600;
}}
QPushButton#pomoBtn, QPushButton#calibBtn {{
    background-color: #eaeaef;
    border: 2px solid #c0c0cc;
    border-radius: {px(18, 12)};
    min-height: {px(36, 24)};
    padding: {px(6, 4)} {px(14, 10)};
    color: #686878;
    font-size: {px(11, 8)};
    font-weight: 600;
}}
QPushButton#classifyBtn:hover, QPushButton#pomoBtn:hover, QPushButton#calibBtn:hover {{
    border-color: #3d6fd4;
    color: #3d6fd4;
    background-color: rgba(61, 111, 212, 0.10);
}}
QPushButton#pomoBtn[active="true"], QPushButton#calibBtn[active="true"] {{
    border-color: #3d6fd4;
    border-radius: {px(18, 12)};
    min-height: {px(36, 24)};
    color: #2a4f9e;
    background-color: rgba(61, 111, 212, 0.14);
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
    _DESIGN_EXTENT = 34.0          # r + ext = 109 < half-size 110 → waves stay in box
    _RING_MIN = 0.16               # min ring thickness — valleys dip deep for big swings
    _BASE_EXT = 0.30               # constant base ring thickness (fraction of ext) —
    #                               always-visible full circle → top gap impossible
    _N_CURVE = 720                 # high-res points for a smooth closed path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = "START"
        self._running = False
        self._hovered = False
        self._pressed = False
        self._active = False
        self._dark = True
        self._ambient = QColor(180, 190, 210)
        self._smooth: list[float] = [0.0] * self.N_BARS
        self._targets: list[float] = [0.0] * self.N_BARS
        self._display: list[float] = [0.0] * self.N_BARS
        # Per-band peak EMA so quiet highs animate as much as bass.
        self._band_peak: list[float] = [1e-3] * self.N_BARS
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
        self._band_peak = [1e-3] * self.N_BARS
        self._timer.start(self._TICK_MS)
        self.update()

    def stop_ring(self, label: str = "START") -> None:
        self._running = False
        self._label = label
        self._active = False
        self._timer.stop()
        self._smooth = [0.0] * self.N_BARS
        self._display = [0.0] * self.N_BARS
        self._band_peak = [1e-3] * self.N_BARS

    def set_label(self, label: str) -> None:
        """Update the centre label without disturbing the ring animation."""
        self._label = label
        self.update()

    def set_dark_mode(self, enabled: bool) -> None:
        """Switch the label text colour to match dark / light themes."""
        self._dark = enabled
        self.update()
        self.update()

    def set_bands(self, bands: list[float]) -> None:
        if len(bands) != self.N_BARS:
            return
        self._targets = self._normalize_ring_bands(bands)

    def _normalize_ring_bands(self, bands: list[float]) -> list[float]:
        """Level and redistribute spectrum energy evenly around the ring.

        Raw FFT bands pile bass into one contiguous arc (the bottom with the
        default angle map). Per-band AGC + mild high boost + interleaved
        placement spread motion around the full edge.
        """
        n = self.N_BARS
        # Mild high-frequency lift so treble isn't drowned by bass.
        tilted = [
            max(0.0, float(v)) * (1.0 + 1.35 * (i / max(n - 1, 1)))
            for i, v in enumerate(bands)
        ]
        # Compress dynamic range a bit before AGC.
        compressed = [v**0.55 for v in tilted]

        leveled: list[float] = []
        peak_decay = 0.965
        peak_attack = 0.35
        for i, v in enumerate(compressed):
            peak = self._band_peak[i]
            if v > peak:
                peak = peak + (v - peak) * peak_attack
            else:
                peak = max(1e-3, peak * peak_decay)
            self._band_peak[i] = peak
            # Per-band floor: the lowest band maps to the top of the ring and
            # can sit near zero, which visually opened a gap there.  Enforcing
            # a floor keeps every arc animated and the ring fully encircled.
            leveled.append(max(0.10, min(1.0, v / peak)))

        # Weave low / mid / high thirds around the circle so correlated bass
        # bins are not clustered into a single lobe.
        return self._interleave_band_thirds(leveled)

    @staticmethod
    def _interleave_band_thirds(bands: list[float]) -> list[float]:
        n = len(bands)
        third = (n + 2) // 3
        groups = [bands[0:third], bands[third : 2 * third], bands[2 * third :]]
        out = [0.0] * n
        idx = 0
        max_len = max((len(g) for g in groups), default=0)
        for k in range(max_len):
            for group in groups:
                if k < len(group) and idx < n:
                    out[idx] = group[k]
                    idx += 1
        return out

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

            # Cosine-interpolated sampling around the ring → C1-smooth outline.
            # Start at top (-π/2); Qt Y grows downward so +sin is bottom.
            outer_pts: list[tuple[float, float]] = []
            for k in range(n_curve):
                angle = -0.5 * pi + 2.0 * pi * k / n_curve
                idx_frac = k / n_curve * n_bands
                i0 = int(idx_frac) % n_bands
                frac = idx_frac - int(idx_frac)
                i1 = (i0 + 1) % n_bands
                # Blend linear ↔ cosine interpolation from smoothness setting
                t_cos = 0.5 - 0.5 * cos(pi * frac)
                t = (1.0 - self._interp_cosine) * frac + self._interp_cosine * t_cos
                amp = amps[i0] * (1.0 - t) + amps[i1] * t
                # Contrast-stretch the amplitude (power < 1 lifts mids, deepens
                # valleys, sharpens peaks) for larger visible fluctuation while
                # the radius stays bounded by ext — the waves never leave the box.
                amp = max(0.0, min(1.0, amp)) ** 1.6
                # Keep a minimum ring thickness even when a band is near-zero,
                # so the ring never fully hugs the button (no empty top gap).
                dist = r + (self._RING_MIN + (1.0 - self._RING_MIN) * amp) * ext
                outer_pts.append((cx + dist * cos(angle), cy + dist * sin(angle)))

            # Inner circle (reversed) to close the ring.
            # Sink 2 px inside the button so the background circle drawn later
            # fully covers the inner seam — no anti-alias gap.
            inner_r = r - 2 * scale
            inner_pts: list[tuple[float, float]] = []
            for k in range(n_curve - 1, -1, -1):
                angle = -0.5 * pi + 2.0 * pi * k / n_curve
                inner_pts.append((cx + inner_r * cos(angle), cy + inner_r * sin(angle)))

            # Two closed subpaths (outer wave + inner circle) with OddEven
            # fill.  A single winding subpath puts a radial seam at the top
            # where the wave collapses; the dense edges there make the
            # scanline filler drop the fill on a small top spot while the
            # outline (drawn separately) still shows.  OddEven on two closed
            # rings has no seam and cannot hollow the band.
            ring_path = QPainterPath()
            ring_path.addPolygon(QPolygonF([QPointF(x, y) for x, y in outer_pts]))
            ring_path.addPolygon(QPolygonF([QPointF(x, y) for x, y in inner_pts]))
            ring_path.setFillRule(Qt.FillRule.OddEvenFill)

            # Radial gradient fill — theme colour (eases with work-type aurora).
            # Bright at the inner edge, fading to a dim, desaturated rim so the
            # band clearly reads as a gradient even at rest.
            theme = self._ambient
            h, s, v, _a = theme.getHsvF()
            if h < 0:
                h = 0.0
            s = min(1.0, max(0.35, s * 1.15 + 0.1))
            v = min(1.0, max(0.55, v * 1.1 + 0.08))

            def _tint(sat: float, val: float, alpha: int, hue_shift: float = 0.0) -> QColor:
                c = QColor()
                c.setHsvF((h + hue_shift) % 1.0, min(1.0, sat), min(1.0, val), 1.0)
                c.setAlpha(alpha)
                return c

            grad = QRadialGradient(cx, cy, r + ext)
            grad.setColorAt(0.0, _tint(s, v, 245))
            grad.setColorAt(r / (r + ext), _tint(s, v, 245))
            grad.setColorAt(0.78, _tint(s * 0.9, v * 0.84, 205, 0.015))
            grad.setColorAt(0.89, _tint(s * 0.68, v * 0.68, 155, 0.025))
            grad.setColorAt(1.0, _tint(s * 0.45, v * 0.5, 115, 0.035))

            # Constant base ring underneath — a fixed-thickness annulus that
            # fully encircles the button at every angle.  Even when the low
            # band (which maps to the top of the ring) is silent, the top arc
            # still shows this base band, so a visible gap can never form.
            base_outer = r + self._BASE_EXT * ext
            base_path = QPainterPath()
            base_path.addEllipse(
                cx - base_outer, cy - base_outer, 2 * base_outer, 2 * base_outer
            )
            base_path.addEllipse(cx - inner_r, cy - inner_r, 2 * inner_r, 2 * inner_r)
            base_path.setFillRule(Qt.FillRule.OddEvenFill)
            base_grad = QRadialGradient(cx, cy, base_outer)
            base_grad.setColorAt(0.0, _tint(s * 0.92, v * 0.95, 175))
            base_grad.setColorAt(1.0, _tint(s * 0.75, v * 0.88, 150))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(base_grad)
            p.drawPath(base_path)

            # Animated wave ring on top of the base ring.
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawPath(ring_path)

            # Subtle outer contour line — closed loop (soft, not a hard border)
            outline_pen = QPen(
                _tint(s, min(1.0, v), 55),
                max(1.0, 0.9 * scale),
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
        # Theme-aware text: white on dark glass, near-black on light glass.
        if self._dark:
            shadow = QColor(0, 0, 0, 90)
            text = QColor(255, 255, 255, 235)
        else:
            shadow = QColor(255, 255, 255, 150)
            text = QColor(18, 18, 26, 235)
        p.setPen(shadow)
        p.drawText(
            text_rect_x,
            text_rect_y + max(1, int(round(scale))),
            text_rect_w,
            text_rect_h,
            Qt.AlignmentFlag.AlignCenter,
            self._label,
        )
        p.setPen(text)
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
    classify_requested = pyqtSignal()  # user wants to classify current window
    pomodoro_start_requested = pyqtSignal(str)
    pomodoro_cancel_requested = pyqtSignal()
    calibrate_requested = pyqtSignal(str)
    calibrate_cancel_requested = pyqtSignal()

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
        self._aurora_brightness_gain = 2.5
        self._blob_count_f = float(self._BLOB_MIN)
        self._blob_rng = Random(7)
        self._blobs = self._make_blobs(self._BLOB_MAX, seed=7)
        self._current_context = WorkContext.UNKNOWN
        self._pomodoro_active = False
        self._calibration_active = False
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
        self._top_stack.setMinimumHeight(72)
        self._top_stack.setMaximumHeight(160)
        self._top_stack.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._top_stack.setStyleSheet("background: transparent;")

        # Page 0: Motto
        motto_w = QWidget()
        motto_w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        motto_w.setStyleSheet("background: transparent;")
        motto_l = QVBoxLayout(motto_w)
        motto_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._motto = QLabel(tr("home_motto"))
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
        self._status_layout.setContentsMargins(0, 0, 0, 0)
        self._status_layout.setSpacing(8)

        focus_row = QHBoxLayout()
        focus_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._focus_title = QLabel(tr("home_focus"))
        self._focus_title.setObjectName("focusTitleLabel")
        self._focus_bar = QProgressBar()
        self._focus_bar.setObjectName("focusBar")
        self._focus_bar.setRange(0, 100)
        self._focus_bar.setTextVisible(False)
        self._focus_bar.setFixedWidth(240)
        self._focus_pct = QLabel("0%")
        self._focus_pct.setObjectName("focusPctLabel")
        focus_row.addWidget(self._focus_title)
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

        # Outside the fixed-height top stack so the full button is never clipped.
        self._classify_btn = QPushButton(tr("home_classify"))
        self._classify_btn.setObjectName("classifyBtn")
        self._classify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._classify_btn.setMinimumWidth(200)
        self._classify_btn.setMinimumHeight(32)
        self._classify_btn.clicked.connect(lambda: self.classify_requested.emit())
        self._classify_btn.setVisible(False)
        self._root.addWidget(self._classify_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # ── Center: circular button with outward EQ bars (needs extra canvas) ──
        self._eq_ring = EqRingWidget()
        self._eq_ring.setFixedSize(self._BTN_DESIGN, self._BTN_DESIGN)
        self._eq_ring.clicked.connect(self._on_action)

        btn_container = QHBoxLayout()
        btn_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_container.addWidget(self._eq_ring)
        self._root.addLayout(btn_container)

        session_row = QHBoxLayout()
        session_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        session_row.setSpacing(10)

        self._pomo_btn = QPushButton(tr("home_pomodoro_idle"))
        self._pomo_btn.setObjectName("pomoBtn")
        self._pomo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pomo_btn.setMinimumWidth(140)
        self._pomo_btn.setMaximumWidth(220)
        self._pomo_btn.setProperty("active", False)
        self._pomo_btn.clicked.connect(self._on_pomodoro_clicked)
        session_row.addWidget(self._pomo_btn)

        self._calib_btn = QPushButton(tr("home_calibrate_idle"))
        self._calib_btn.setObjectName("calibBtn")
        self._calib_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._calib_btn.setMinimumWidth(140)
        self._calib_btn.setMaximumWidth(220)
        self._calib_btn.setProperty("active", False)
        self._calib_btn.setToolTip(tr("home_calibrate_tip"))
        self._calib_btn.clicked.connect(self._on_calibrate_clicked)
        session_row.addWidget(self._calib_btn)

        self._root.addLayout(session_row)

        self._root.addStretch(1)

        self.setStyleSheet(_home_stylesheet(dark=True, scale=1.0))
        self._apply_layout_scale(force=True)

    def resizeEvent(self, event) -> None:  # noqa: N803
        super().resizeEvent(event)
        self._apply_layout_scale()

    def _compute_layout_scale(self) -> float:
        w = max(float(self.width()), 1.0)
        h = max(float(self.height()), 1.0)
        raw = min(w / self._REF_W, h / self._REF_H)
        # Cap growth so fullscreen keeps air around the glass disc.
        return max(0.82, min(1.55, raw))

    def _apply_layout_scale(self, *, force: bool = False) -> None:
        scale = self._compute_layout_scale()
        if not force and abs(scale - self._layout_scale) < 0.02:
            return
        self._layout_scale = scale

        m = max(16, int(round(28 * scale)))
        self._root.setContentsMargins(m, m, m, m)
        self._root.setSpacing(max(8, int(round(12 * scale))))
        self._status_layout.setSpacing(max(4, int(round(8 * scale))))

        # Soft height bounds — let status text breathe without a hard clip box.
        top_min = max(64, int(round(72 * scale)))
        top_max = max(top_min + 24, int(round(140 * scale)))
        self._top_stack.setMinimumHeight(top_min)
        self._top_stack.setMaximumHeight(top_max)

        # Cap ring by leftover vertical space so session buttons never get crushed.
        session_h = 48
        classify_h = 40 if self._classify_btn.isVisible() else 0
        margins = 2 * m + 80
        leftover = max(140.0, float(self.height()) - top_max - session_h - classify_h - margins)
        btn = int(round(min(self._BTN_DESIGN * scale, leftover)))
        btn = max(150, min(280, btn))
        self._eq_ring.setFixedSize(btn, btn)

        self._focus_bar.setFixedWidth(max(160, int(round(220 * scale))))
        self._classify_btn.setMinimumWidth(max(180, int(round(200 * scale))))
        self._classify_btn.setMinimumHeight(max(30, int(round(32 * scale))))

        self.setStyleSheet(_home_stylesheet(dark=self._dark, scale=scale))
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
        # Focus tints the whole background toward the theme colour so the
        # change in focus level is clearly visible even outside the blobs.
        if self._focus_level > 0.01:
            tint = QColor(self._aurora_color)
            f = self._focus_level * 0.22
            base = QColor(
                int(base.red() + (tint.red() - base.red()) * f),
                int(base.green() + (tint.green() - base.green()) * f),
                int(base.blue() + (tint.blue() - base.blue()) * f),
            )
        p.fillRect(self.rect(), base)

        def _scaled_alpha(a: int) -> int:
            return int(min(255, max(0, round(a * bright))))

        # Subtle vertical wash so blobs feel layered in depth
        wash = QLinearGradient(0, 0, 0, h)
        theme = QColor(self._aurora_color)
        if self._dark:
            wash.setColorAt(0.0, QColor(theme.red(), theme.green(), theme.blue(), _scaled_alpha(30)))
            wash.setColorAt(0.55, QColor(theme.red(), theme.green(), theme.blue(), _scaled_alpha(10)))
            wash.setColorAt(1.0, QColor(0, 0, 0, 40))
        else:
            wash.setColorAt(0.0, QColor(theme.red(), theme.green(), theme.blue(), _scaled_alpha(48)))
            wash.setColorAt(0.6, QColor(theme.red(), theme.green(), theme.blue(), _scaled_alpha(18)))
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
            if self._dark:
                s = min(1.0, max(0.0, s * blob.sat_scale + 0.15))
                # Focus lifts luminance of the flowing lights
                v_boost = 1.0 + 0.45 * self._focus_level * self._aurora_brightness_gain
                v = min(1.0, v * 1.05 * v_boost)
            else:
                # Bright theme: keep the hue saturated but darken the colour so
                # the orbs read clearly against the pale base instead of
                # washing out toward white.
                s = min(1.0, max(0.0, s * blob.sat_scale + 0.18))
                v_boost = 1.0 + 0.30 * self._focus_level * self._aurora_brightness_gain
                v = min(1.0, max(0.22, v * 0.45 / v_boost))
            c.setHsvF(h_deg, s, v)

            alpha = blob.alpha if self._dark else int(blob.alpha * 0.95)
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

    def _task_profile(self) -> str:
        profile = self._current_context.value
        if profile == WorkContext.DISTRACTION.value:
            return WorkContext.UNKNOWN.value
        return profile

    def _on_pomodoro_clicked(self) -> None:
        if self._pomodoro_active:
            self.pomodoro_cancel_requested.emit()
            return
        self.pomodoro_start_requested.emit(self._task_profile())

    def _on_calibrate_clicked(self) -> None:
        if self._calibration_active:
            self.calibrate_cancel_requested.emit()
            return
        self.calibrate_requested.emit(self._task_profile())

    @staticmethod
    def _sync_session_button(
        button: QPushButton,
        *,
        active_flag_attr: str,
        active: bool,
        idle_text: str,
        active_text: str,
        owner: "HomePage",
    ) -> None:
        active = bool(active)
        text = active_text if active else idle_text
        if getattr(owner, active_flag_attr) == active and button.text() == text:
            return
        setattr(owner, active_flag_attr, active)
        button.setText(text)
        button.setProperty("active", active)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def set_pomodoro_active(self, active: bool, *, label: str | None = None) -> None:
        """Sync Pomodoro button label/state from the app controller."""
        self._sync_session_button(
            self._pomo_btn,
            active_flag_attr="_pomodoro_active",
            active=active,
            idle_text=tr("home_pomodoro_idle"),
            active_text=label or tr("home_pomodoro_active"),
            owner=self,
        )

    def set_calibration_active(self, active: bool, *, label: str | None = None) -> None:
        """Sync dedicated calibration button label/state from the app controller."""
        self._sync_session_button(
            self._calib_btn,
            active_flag_attr="_calibration_active",
            active=active,
            idle_text=tr("home_calibrate_idle"),
            active_text=label or tr("home_calibrate_active"),
            owner=self,
        )

    def set_running(self, running: bool) -> None:
        """Sync button text, colour, and top-area content from the app."""
        if self._running == running:
            return
        self._running = running
        if running:
            self._eq_ring.start_ring(tr("ring_stop"))
            self._top_stack.setCurrentIndex(1)
        else:
            self._eq_ring.stop_ring(tr("ring_start"))
            self._top_stack.setCurrentIndex(0)
            self._classify_btn.setVisible(False)
        self._apply_layout_scale(force=True)

    def set_language(self, code: str) -> None:
        """Switch UI language and retranslate the page's static strings."""
        i18n_set_language(code)
        self._retranslate()

    def _retranslate(self) -> None:
        """Re-apply the active language to home page static strings."""
        self._motto.setText(tr("home_motto"))
        self._focus_title.setText(tr("home_focus"))
        self._classify_btn.setText(tr("home_classify"))
        self._calib_btn.setToolTip(tr("home_calibrate_tip"))
        self._sync_session_button(
            self._pomo_btn,
            active_flag_attr="_pomodoro_active",
            active=self._pomodoro_active,
            idle_text=tr("home_pomodoro_idle"),
            active_text=tr("home_pomodoro_active"),
            owner=self,
        )
        self._sync_session_button(
            self._calib_btn,
            active_flag_attr="_calibration_active",
            active=self._calibration_active,
            idle_text=tr("home_calibrate_idle"),
            active_text=tr("home_calibrate_active"),
            owner=self,
        )
        self._eq_ring.set_label(tr("ring_stop") if self._running else tr("ring_start"))

    def set_frequency_bands(self, bands: list[float]) -> None:
        """Forward real-time frequency-band amplitudes to the EQ ring."""
        self._eq_ring.set_bands(bands)

    def set_waveform_smoothness(self, value: float) -> None:
        """Forward Settings slider (0–1) to the EQ ring."""
        self._eq_ring.set_smoothness(value)

    def set_classify_available(self, available: bool) -> None:
        """Show/hide the 'Confirm Classification' button."""
        visible = available and self._running
        if self._classify_btn.isVisible() == visible:
            return
        self._classify_btn.setVisible(visible)
        self._apply_layout_scale(force=True)

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

        self._current_context = context

        if not self._running:
            return

        pct = int(max(0.0, min(1.0, focus_score)) * 100)
        self._focus_bar.setValue(pct)
        self._focus_pct.setText(f"{pct}%")

        theme = i18n_theme_label(context.value)
        if music_state:
            mood = music_state
        elif pct >= 80:
            mood = tr("mood_deep_focus")
        elif pct >= 60:
            mood = tr("mood_in_the_zone")
        elif pct >= 40:
            mood = tr("mood_light_focus")
        elif pct >= 20:
            mood = tr("mood_wandering")
        else:
            mood = tr("mood_distracted")

        self._theme_label.setText(f"{theme}  ·  {mood}")
        self._music_detail.setText(music_detail)
        self._music_detail.setVisible(bool(music_detail))

    # ------------------------------------------------------------------
    # Theme switching
    # ------------------------------------------------------------------

    def set_dark_mode(self, enabled: bool) -> None:
        """Apply dark / light stylesheet on the home page."""
        self._dark = enabled
        self._eq_ring.set_dark_mode(enabled)
        self._apply_layout_scale(force=True)
        self.update()

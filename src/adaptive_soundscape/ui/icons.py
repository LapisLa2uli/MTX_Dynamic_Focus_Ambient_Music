"""Profile tab icons for the upload page.

Icons are bundled SVG assets from the Lucide icon set (permissively
licensed, see the ``@license`` comment inside each SVG) and rendered at
runtime. Each icon is recolored per theme by replacing ``currentColor``
with the requested stroke color, so the same asset works on dark and
light backgrounds.

If an SVG file is missing (e.g. a partial copy of the repo) the module
falls back to the QPainter line drawings that were used before.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from PyQt6.QtCore import QByteArray, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtSvg import QSvgRenderer

CANVAS = 48
_STROKE = 3.2
_ICON_DIR = os.path.join(os.path.dirname(__file__), "icons")

#: profile_id -> bundled SVG asset (Lucide, stroke="currentColor").
_ICON_FILES: dict[str, str] = {
    "programming": "programming.svg",
    "team_workflow": "team_workflow.svg",
    "reading_writing": "reading_writing.svg",
    "scientific": "scientific.svg",
    "creative_design": "creative_design.svg",
    "distraction": "distraction.svg",
    "unknown": "unknown.svg",
}


def _svg_pixmap(path: str, color_hex: str) -> QPixmap | None:
    """Render an SVG file into a transparent canvas, recolored for the theme.

    Returns ``None`` when the file cannot be read or parsed so callers can
    fall back to the vector drawings.
    """
    try:
        with open(path, encoding="utf-8") as f:
            xml = f.read()
    except OSError:
        return None
    try:
        renderer = QSvgRenderer(QByteArray(xml.replace("currentColor", color_hex).encode("utf-8")))
    except Exception:
        return None
    if not renderer.isValid():
        return None
    pixmap = QPixmap(CANVAS, CANVAS)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, CANVAS, CANVAS))
    painter.end()
    return pixmap


# ---------------------------------------------------------------------------
# Fallback drawings (used only when an SVG asset is missing).
# ---------------------------------------------------------------------------

def _pen(color: QColor) -> QPen:
    pen = QPen(color, _STROKE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_terminal(painter: QPainter, color: QColor) -> None:
    """Terminal window with a '>_' prompt (programming)."""
    painter.drawRoundedRect(QRectF(11, 13, 26, 22), 4, 4)
    path = QPainterPath()
    path.moveTo(17, 21)
    path.lineTo(23, 27)
    path.lineTo(17, 33)
    painter.drawPath(path)
    painter.drawLine(QPointF(25, 32), QPointF(33, 32))


def _draw_users(painter: QPainter, color: QColor) -> None:
    """Two overlapping people silhouettes (team workflow)."""
    painter.drawEllipse(QPointF(17, 17), 5, 5)
    front = QPainterPath()
    front.moveTo(10, 35)
    front.cubicTo(14, 29, 20, 29, 24, 35)
    painter.drawPath(front)
    painter.drawEllipse(QPointF(31, 22), 4, 4)
    back = QPainterPath()
    back.moveTo(26, 36)
    back.cubicTo(29, 32, 33, 32, 36, 36)
    painter.drawPath(back)


def _draw_book(painter: QPainter, color: QColor) -> None:
    """Open book (reading & writing)."""
    left = QPainterPath()
    left.moveTo(9, 19)
    left.lineTo(24, 17)
    left.lineTo(24, 35)
    left.lineTo(9, 33)
    painter.drawPath(left)
    right = QPainterPath()
    right.moveTo(39, 19)
    right.lineTo(24, 17)
    right.lineTo(24, 35)
    right.lineTo(39, 33)
    painter.drawPath(right)
    painter.drawLine(QPointF(24, 17), QPointF(24, 35))


def _draw_flask(painter: QPainter, color: QColor) -> None:
    """Erlenmeyer-style flask (scientific)."""
    path = QPainterPath()
    path.moveTo(18, 14)
    path.lineTo(18, 25)
    path.lineTo(11, 34)
    path.quadTo(17, 40, 24, 40)
    path.quadTo(31, 40, 37, 34)
    path.lineTo(30, 25)
    path.lineTo(30, 14)
    painter.drawPath(path)
    painter.drawLine(QPointF(18, 14), QPointF(30, 14))


def _draw_pen(painter: QPainter, color: QColor) -> None:
    """Pen-tool diamond with nib dot (creative design)."""
    diamond = QPainterPath()
    diamond.moveTo(24, 13)
    diamond.lineTo(35, 24)
    diamond.lineTo(24, 35)
    diamond.lineTo(13, 24)
    diamond.closeSubpath()
    painter.drawPath(diamond)
    painter.setBrush(color)
    painter.drawEllipse(QPointF(24, 31), 2.2, 2.2)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _draw_alert(painter: QPainter, color: QColor) -> None:
    """Warning triangle with exclamation mark (distraction)."""
    triangle = QPainterPath()
    triangle.moveTo(24, 13)
    triangle.lineTo(36, 35)
    triangle.lineTo(12, 35)
    triangle.closeSubpath()
    painter.drawPath(triangle)
    painter.drawLine(QPointF(24, 21), QPointF(24, 28))
    painter.setBrush(color)
    painter.drawEllipse(QPointF(24, 31), 1.6, 1.6)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _draw_circle(painter: QPainter, color: QColor) -> None:
    """Plain ring (neutral / unknown)."""
    painter.drawEllipse(QPointF(24, 24), 9, 9)


_DRAWERS: dict[str, Callable[[QPainter, QColor], None]] = {
    "programming": _draw_terminal,
    "team_workflow": _draw_users,
    "reading_writing": _draw_book,
    "scientific": _draw_flask,
    "creative_design": _draw_pen,
    "distraction": _draw_alert,
    "unknown": _draw_circle,
}


def _make_icon(color_hex: str, drawer: Callable[[QPainter, QColor], None]) -> QIcon:
    color = QColor(color_hex)
    pixmap = QPixmap(CANVAS, CANVAS)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(_pen(color))
    drawer(painter, color)
    painter.end()
    return QIcon(pixmap)


def build_profile_icons(color_hex: str) -> dict[str, QIcon]:
    """Return {profile_id: QIcon} for every cognitive-status profile.

    Prefers the bundled Lucide SVG asset for each profile and falls back to
    the QPainter drawing only if the SVG is unavailable.
    """
    icons: dict[str, QIcon] = {}
    for pid, fname in _ICON_FILES.items():
        pixmap = _svg_pixmap(os.path.join(_ICON_DIR, fname), color_hex)
        icons[pid] = QIcon(pixmap) if pixmap is not None else _make_icon(color_hex, _DRAWERS[pid])
    return icons

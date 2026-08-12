import sys

sys.path.insert(0, "src")
from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtGui import QImage, QPainter, QColor
from PyQt6.QtCore import Qt

from adaptive_soundscape.ui.home_page import _home_stylesheet

app = QApplication([])

dark = _home_stylesheet(dark=True, scale=1.0)


def render_button(active: bool, path: str) -> None:
    btn = QPushButton("End Pomodoro" if active else "Start Pomodoro")
    btn.setObjectName("pomoBtn")
    btn.setProperty("active", active)
    btn.setFixedSize(168, 26)
    btn.setStyleSheet(dark)
    img = QImage(200, 60, QImage.Format.Format_ARGB32)
    img.fill(QColor(20, 20, 26))
    p = QPainter(img)
    btn.render(p)
    p.end()
    img.save(path)
    print("saved", path)


render_button(False, "scripts/diag_idle.png")
render_button(True, "scripts/diag_active.png")

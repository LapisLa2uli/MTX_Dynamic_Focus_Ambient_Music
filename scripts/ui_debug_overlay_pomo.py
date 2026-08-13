"""UI debug: Pomodoro diminishing ring + floating overlay.

```powershell
conda activate MTX
python scripts/ui_debug_overlay_pomo.py
```
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.text.font.db.debug=false;qt.text.font.db.info=false;qt.text.font.db.warning=false",
)

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adaptive_soundscape.app import AdaptiveSoundscapeApp  # noqa: E402
from adaptive_soundscape.core.config import load_settings  # noqa: E402

FAILURES: list[str] = []


def log(msg: str) -> None:
    print(f"[hud-ui] {msg}", flush=True)


def fail(msg: str) -> None:
    log(f"FAIL: {msg}")
    FAILURES.append(msg)


def ok(msg: str) -> None:
    log(f"OK: {msg}")


def pump(app: QApplication, ms: int = 80) -> None:
    app.processEvents()
    QTest.qWait(ms)
    app.processEvents()


def click(w, app: QApplication) -> None:
    QTest.mouseClick(w, Qt.MouseButton.LeftButton)
    pump(app, 120)


def main() -> int:
    app = QApplication(sys.argv)
    from PyQt6.QtCore import QTimer

    def _dismiss() -> None:
        for w in app.topLevelWidgets():
            if isinstance(w, QMessageBox) and w.isVisible():
                w.accept()

    t = QTimer()
    t.timeout.connect(_dismiss)
    t.start(200)
    app._t = t

    settings = load_settings()
    soundscape = AdaptiveSoundscapeApp(settings=settings)
    soundscape.start()
    soundscape.window.show()
    pump(app, 350)

    overlay = soundscape._overlay
    flags = overlay.windowFlags()
    if not (flags & Qt.WindowType.WindowStaysOnTopHint):
        fail("overlay missing WindowStaysOnTopHint")
    else:
        ok("overlay stays on top")
    if not overlay.isVisible():
        fail("overlay not shown")
    else:
        ok("overlay visible")

    # Drag
    before = overlay.pos()
    overlay.move(before + QPoint(-24, 18))
    pump(app, 80)
    if overlay.pos() == before:
        fail("overlay did not move")
    else:
        ok("overlay is movable")
    overlay.resize(268, 116)
    pump(app, 80)
    if overlay.width() < 250:
        fail(f"overlay resize failed w={overlay.width()}")
    else:
        ok("overlay is resizable")

    if "font-size: 24px" not in overlay.styleSheet():
        fail("mini HUD timer stylesheet is not 24px")
    else:
        ok("mini HUD timer is 24px")

    ring = soundscape.window.home_page._eq_ring
    cx, cy, r, gap, ext = ring._geom()
    if gap < 4:
        fail(f"pomo gap too small: {gap}")
    else:
        ok(f"waveform lifted; pomo gap={gap:.1f}px")

    click(soundscape.window.home_page._pomo_btn, app)
    pump(app, 400)
    if not soundscape.pomodoro.state.is_active:
        fail("pomodoro did not start")
    else:
        ok("pomodoro started")
        frac = soundscape.pomodoro.state.remaining_fraction
        if frac < 0.9:
            fail(f"remaining_fraction={frac} expected ~1")
        else:
            ok(f"remaining_fraction={frac:.2f}")
        if not ring._pomo_active:
            fail("eq ring pomo inactive")
        else:
            ok("diminishing pomo edge armed on EQ ring")
        pump(app, 400)
        if ring._pomo_fade < 0.35:
            fail(f"pomo ring fade-in too low: {ring._pomo_fade:.2f}")
        else:
            ok(f"pomo ring faded in ({ring._pomo_fade:.2f})")
        time_text = overlay._pomo_time.text()
        if ":" not in time_text:
            fail(f"overlay timer text={time_text!r}")
        else:
            ok(f"overlay timer {time_text}")

    click(soundscape.window.home_page._pomo_btn, app)
    pump(app, 200)
    if soundscape.pomodoro.state.is_active:
        fail("pomodoro did not cancel")
    else:
        ok("pomodoro cancelled; ring cleared")

    soundscape.stop()
    pump(app, 100)
    if overlay.isVisible():
        fail("overlay still visible after stop")
    else:
        ok("overlay hidden on shutdown")

    if FAILURES:
        log(f"{len(FAILURES)} failure(s)")
        return 1
    log("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

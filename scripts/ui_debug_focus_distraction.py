"""UI debug: focus override → auto-distraction → recovery.

```powershell
conda activate MTX
python scripts/ui_debug_focus_distraction.py
```
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.text.font.db.debug=false;qt.text.font.db.info=false;qt.text.font.db.warning=false",
)

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adaptive_soundscape.app import AdaptiveSoundscapeApp  # noqa: E402
from adaptive_soundscape.core.config import load_settings  # noqa: E402
from adaptive_soundscape.core.events import WorkContext  # noqa: E402

FAILURES: list[str] = []


def log(msg: str) -> None:
    print(f"[focus-ui] {msg}", flush=True)


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
    pump(app, 100)


def main() -> int:
    app = QApplication(sys.argv)
    # Auto-dismiss message boxes
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
    # Fast dwell for interactive debug
    settings.cognitive.auto_distraction_dwell_seconds = 1.0
    settings.cognitive.auto_distraction_enter = 0.38
    settings.cognitive.auto_distraction_exit = 0.50

    soundscape = AdaptiveSoundscapeApp(settings=settings)
    soundscape.start()
    soundscape.window.show()
    pump(app, 300)
    ok("window shown")

    # Layout smoke: navigate all pages
    for i, name in enumerate(("home", "upload", "settings")):
        click(soundscape.window._nav_buttons[i], app)
        ok(f"nav → {name}")

    sp = soundscape.window.settings_page
    # Debug section: layer sliders hidden until ON
    if getattr(sp, "_layer_sliders_host", None) is not None:
        if sp._layer_sliders_host.isVisible():
            fail("layer sliders visible before toggle")
        else:
            ok("debug layer sliders collapsed by default")

    # Enable manual concentration low
    click(sp._debug_focus_toggle, app)
    sp._debug_focus_slider.setValue(15)
    pump(app, 150)
    if not soundscape._debug_focus_override:
        fail("debug focus not enabled")
    else:
        ok(f"debug focus @ {soundscape._debug_focus_score:.2f}")

    # Start audio so transitions are exercised
    click(soundscape.window._nav_buttons[0], app)
    click(soundscape.window.home_page._eq_ring, app)
    pump(app, 400)
    ok(f"audio running={soundscape._audio_running}")

    # Tick until auto-distraction fires (~1s dwell)
    entered = False
    for i in range(20):
        soundscape._tick()
        pump(app, 120)
        if soundscape._auto_distract_active:
            entered = True
            ok(
                f"auto-distraction active after {i+1} ticks; "
                f"ctx={soundscape._current_context.value} "
                f"focus={soundscape._focus_score:.2f}"
            )
            break
    if not entered:
        fail("auto-distraction never activated at low debug focus")
    elif soundscape._current_context != WorkContext.DISTRACTION:
        fail(f"expected DISTRACTION context, got {soundscape._current_context}")

    # Raise focus and wait for exit
    click(soundscape.window._nav_buttons[2], app)
    sp._debug_focus_slider.setValue(85)
    pump(app, 150)
    left = False
    for i in range(25):
        soundscape._tick()
        pump(app, 120)
        if not soundscape._auto_distract_active:
            left = True
            ok(
                f"left auto-distraction after {i+1} ticks; "
                f"ctx={soundscape._current_context.value} "
                f"focus={soundscape._focus_score:.2f}"
            )
            break
    if not left:
        fail("auto-distraction did not clear after high focus")

    # Sensitivity slider still wired
    sp._threshold_slider.setValue(150)
    pump(app, 100)
    if abs(soundscape.focus_index.sensitivity - 1.5) > 0.05:
        fail(f"sensitivity not applied: {soundscape.focus_index.sensitivity}")
    else:
        ok("concentration threshold → FLI sensitivity")

    click(sp._debug_focus_toggle, app)  # off
    if soundscape._audio_running:
        soundscape.window.home_page.action_toggled.emit(False)
        pump(app, 200)
    soundscape.stop()

    if FAILURES:
        log(f"RESULT: {len(FAILURES)} failure(s)")
        for f in FAILURES:
            log(f"  - {f}")
        return 1
    log("RESULT: focus/auto-distraction UI paths OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

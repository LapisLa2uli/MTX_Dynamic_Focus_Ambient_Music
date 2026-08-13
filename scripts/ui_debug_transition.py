"""UI debug: context blend slider + scenario switch does not crash the mixer.

```powershell
conda activate MTX
python scripts/ui_debug_transition.py
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
    print(f"[xfade-ui] {msg}", flush=True)


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
    pump(app, 300)

    click(soundscape.window._nav_buttons[2], app)
    sp = soundscape.window.settings_page
    if getattr(sp, "_scenario_xfade_slider", None) is None:
        fail("missing Context blend time slider")
        return 1
    ok("context blend slider present")

    sp._scenario_xfade_slider.setValue(250)
    pump(app, 150)
    if abs(soundscape.director.config.scenario_crossfade_seconds - 2.5) > 0.08:
        fail(
            f"scenario_crossfade={soundscape.director.config.scenario_crossfade_seconds}"
        )
    else:
        ok("context blend time → 2.5s")

    sp._scenario_xfade_slider.setValue(400)
    pump(app, 120)
    ok("restored 4.0s blend")

    # Start audio then force two scenario hops (equal-power path).
    click(soundscape.window._nav_buttons[0], app)
    click(soundscape.window.home_page._eq_ring, app)
    pump(app, 400)
    if not soundscape._audio_running:
        fail("audio did not start")
    else:
        ok("audio started")

    for ctx in (WorkContext.PROGRAMMING, WorkContext.SCIENTIFIC, WorkContext.DISTRACTION):
        decision = soundscape.transition.force_profile(ctx, soundscape._current_focus)
        soundscape._apply_audio(decision)
        pump(app, 350)
        ok(f"switched context → {ctx.value}")

    overlay = getattr(soundscape, "_overlay", None)
    if overlay is None or not overlay.isVisible():
        fail("mini overlay not visible")
    else:
        ok("mini overlay visible on top")
        overlay.set_focus(0.42)
        pump(app, 80)
        if overlay._bar.value() != 42:
            fail(f"overlay focus bar={overlay._bar.value()}")
        else:
            ok("overlay focus meter updated")

    soundscape.stop()
    pump(app, 100)
    if FAILURES:
        log(f"{len(FAILURES)} failure(s)")
        return 1
    log("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

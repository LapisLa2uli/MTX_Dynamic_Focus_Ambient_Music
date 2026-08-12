"""UI debug: Settings → Effect response sliders wire into live app state.

```powershell
conda activate MTX
python scripts/ui_debug_effects.py
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

FAILURES: list[str] = []


def log(msg: str) -> None:
    print(f"[effects-ui] {msg}", flush=True)


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


def set_slider(slider, value: int, app: QApplication) -> None:
    slider.setValue(value)
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
    ok("window shown")

    click(soundscape.window._nav_buttons[2], app)
    ok("nav → settings")

    sp = soundscape.window.settings_page
    for name in (
        "_muffle_curve_slider",
        "_intensity_smooth_slider",
        "_gain_slew_slider",
        "_focus_smooth_slider",
    ):
        if getattr(sp, name, None) is None:
            fail(f"missing slider {name}")
            return 1
    ok("effect response sliders present")

    set_slider(sp._muffle_curve_slider, 450, app)
    if abs(soundscape._muffling_curve - 4.5) > 0.05:
        fail(f"muffling curve={soundscape._muffling_curve}, expected ~4.5")
    else:
        ok(f"muffling aggressiveness → {soundscape._muffling_curve:.1f}×")

    set_slider(sp._intensity_smooth_slider, 20, app)
    if abs(soundscape.director.config.intensity_smoothing - 0.20) > 0.02:
        fail(
            f"intensity_smoothing={soundscape.director.config.intensity_smoothing}"
        )
    else:
        ok(
            f"music intensity lag → {soundscape.director.config.intensity_smoothing:.2f}"
        )

    set_slider(sp._gain_slew_slider, 50, app)
    if abs(soundscape.director.config.gain_slew_seconds - 0.5) > 0.05:
        fail(f"gain_slew={soundscape.director.config.gain_slew_seconds}")
    else:
        ok(f"layer blend time → {soundscape.director.config.gain_slew_seconds:.1f}s")

    set_slider(sp._focus_smooth_slider, 15, app)
    if abs(soundscape.focus_index.smoothing - 0.15) > 0.02:
        fail(f"focus_smoothing={soundscape.focus_index.smoothing}")
    else:
        ok(f"focus bar lag → {soundscape.focus_index.smoothing:.2f}")

    # Restore snappy defaults used in yaml
    set_slider(sp._muffle_curve_slider, 300, app)
    set_slider(sp._intensity_smooth_slider, 35, app)
    set_slider(sp._gain_slew_slider, 100, app)
    set_slider(sp._focus_smooth_slider, 40, app)
    ok("restored default effect slider values")

    soundscape.stop()
    pump(app, 100)

    if FAILURES:
        log(f"{len(FAILURES)} failure(s)")
        for f in FAILURES:
            log(f"  - {f}")
        return 1
    log("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

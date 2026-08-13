"""UI debug: Confirm Classification opens a right-side unclassified list.

```powershell
conda activate MTX
python scripts/ui_debug_classify_panel.py
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
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adaptive_soundscape.app import AdaptiveSoundscapeApp  # noqa: E402
from adaptive_soundscape.context.user_mappings import (  # noqa: E402
    load_user_mappings,
    save_user_mappings,
)
from adaptive_soundscape.core.config import load_settings  # noqa: E402
from adaptive_soundscape.core.events import WorkContext  # noqa: E402

FAILURES: list[str] = []
FAKE_PROCESS = "qzxtool999.exe"
FAKE_TITLE = "Strange Tool QZX"


def log(msg: str) -> None:
    print(f"[classify-ui] {msg}", flush=True)


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

    backup = load_user_mappings()
    settings = load_settings()
    soundscape = AdaptiveSoundscapeApp(settings=settings)
    try:
        return _run(app, soundscape)
    finally:
        try:
            soundscape.stop()
        except Exception:
            pass
        pump(app, 80)
        save_user_mappings(backup)
        log("restored previous user mappings")


def _run(app: QApplication, soundscape: AdaptiveSoundscapeApp) -> int:
    soundscape.start()
    soundscape.window.show()
    pump(app, 300)

    panel = soundscape.window.classification_panel
    if panel.isVisible():
        fail("classification panel visible at launch")
    else:
        ok("panel hidden at launch")

    geo = soundscape.window.geometry()
    panel_geo = panel.geometry()
    if panel_geo.x() < geo.width() // 2 and panel.isVisible():
        fail("panel is not on the right")

    home = soundscape.window.home_page
    home._eq_ring.clicked.emit()
    pump(app, 400)
    if not soundscape._audio_running:
        fail("audio did not start")
    else:
        ok("audio started")

    soundscape._seen_windows[("qzxtool999", FAKE_TITLE.lower())] = (
        FAKE_PROCESS,
        FAKE_TITLE,
    )
    home.set_classify_available(True)
    pump(app, 80)
    click(home._classify_btn, app)
    pump(app, 250)

    if not panel.isVisible():
        fail("panel did not open")
        return 1
    ok("panel opened on Confirm Classification")

    if panel.x() < soundscape.window._content_host.x():
        fail("panel is not to the right of the main content")
    else:
        ok("panel is docked on the right")

    labels = [row.process_name for row in panel._rows]
    if FAKE_PROCESS not in labels:
        fail(f"fake window missing from panel: {labels}")
        return 1
    ok("unclassified window listed with suggested category")

    row = next((r for r in panel._rows if r.process_name == FAKE_PROCESS), None)
    if row is None:
        fail("could not find fake window row")
        return 1
    idx = row._combo.findData(WorkContext.SCIENTIFIC.value)
    if idx >= 0:
        row._combo.setCurrentIndex(idx)
    save_btn = row.findChild(QPushButton, "classifySave")
    if save_btn is None:
        fail("row missing Save button")
    else:
        click(save_btn, app)
        pump(app, 200)
        mapped = load_user_mappings()
        names = [p.lower() for p in mapped.get(WorkContext.SCIENTIFIC).process_names]
        if "qzxtool999" not in names:
            fail(f"save did not persist mapping: {names}")
        else:
            ok("per-row Save persisted mapping")
        still = [r.process_name for r in panel._rows]
        if FAKE_PROCESS in still:
            fail("saved window still listed")
        else:
            ok("saved window removed from the list")

    panel.hide_panel()
    pump(app, 80)
    if panel.isVisible():
        fail("panel still visible after close")
    else:
        ok("panel closed")

    if FAILURES:
        log(f"{len(FAILURES)} failure(s)")
        return 1
    log("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

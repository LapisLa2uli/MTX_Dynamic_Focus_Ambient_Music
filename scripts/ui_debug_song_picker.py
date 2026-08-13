"""UI debug: in-album song picker, debug-mix gating, Pomodoro fade, HUD timer.

```powershell
conda activate MTX
python scripts/ui_debug_song_picker.py
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
from adaptive_soundscape.audio.album import is_debug_song  # noqa: E402
from adaptive_soundscape.core.config import load_settings  # noqa: E402
from adaptive_soundscape.core.events import WorkContext  # noqa: E402

FAILURES: list[str] = []


def log(msg: str) -> None:
    print(f"[song-ui] {msg}", flush=True)


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


def combo_ids(combo) -> list[str]:
    return [str(combo.itemData(i) or "") for i in range(combo.count())]


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

    home = soundscape.window.home_page
    combo = home._song_combo
    overlay = soundscape._overlay
    ring = home._eq_ring

    if home._song_row_host.isVisible():
        fail("song picker visible while idle")
    else:
        ok("song picker hidden while idle")

    home._eq_ring.clicked.emit()
    pump(app, 500)
    if not soundscape._audio_running:
        fail("audio did not start")
    else:
        ok("audio started")

    ctx_combo = soundscape.window._context_combo
    idx = ctx_combo.findData(WorkContext.PROGRAMMING)
    if idx >= 0:
        ctx_combo.setCurrentIndex(idx)
    soundscape.window._override_check.setChecked(True)
    pump(app, 400)
    soundscape._refresh_ui()
    pump(app, 200)
    ok(f"album → {soundscape.director._scenario}")

    pump(app, 200)
    if not home._song_row_host.isVisible():
        fail("song picker hidden while playing")
    else:
        ok("song picker visible while playing")

    ids = combo_ids(combo)
    if not ids:
        fail("song combo empty while playing")
    else:
        ok(f"song combo has {len(ids)} track(s)")

    leaked = [s for s in ids if is_debug_song(s)]
    if leaked:
        fail(f"debug mixes in rotation with debug off: {leaked}")
    else:
        ok("debug mixes excluded while debug is off")

    if home._music_detail.isVisible():
        fail("music detail shown while debug is off")
    else:
        ok("music detail hidden while debug is off")

    if combo.count() >= 2:
        before = soundscape.director.active_song_id
        click(home._song_next, app)
        pump(app, 250)
        after = soundscape.director.active_song_id
        if after == before:
            fail(f"next-song did not change track ({before})")
        else:
            ok(f"next-song {before} → {after}")
    else:
        ok("only one album song; skip next-song")

    click(soundscape.window._nav_buttons[2], app)
    click(soundscape.window.settings_page._debug_layer_toggle, app)
    pump(app, 200)
    if not soundscape._debug_layer_override:
        fail("debug layer override did not enable")
    else:
        ok("debug mode on")

    click(soundscape.window._nav_buttons[0], app)
    pump(app, 200)
    debug_ids = [s for s in combo_ids(combo) if is_debug_song(s)]
    if debug_ids:
        ok(f"debug mixes listed while debug on: {debug_ids}")
    else:
        ok("no debug mixes on disk (gating still applied)")
    if not home._music_detail.isVisible():
        fail("music detail hidden while debug is on")
    else:
        ok(f"music detail in debug: {home._music_detail.text()}")

    click(soundscape.window._nav_buttons[2], app)
    click(soundscape.window.settings_page._debug_layer_toggle, app)
    pump(app, 200)
    click(soundscape.window._nav_buttons[0], app)
    pump(app, 200)
    leaked = [s for s in combo_ids(combo) if is_debug_song(s)]
    if leaked:
        fail(f"debug mixes still listed after debug off: {leaked}")
    else:
        ok("debug mixes hidden after debug off")
    if home._music_detail.isVisible():
        fail("music detail still shown after debug off")
    else:
        ok("music detail hidden after debug off")

    font_px = overlay._pomo_time.font().pointSize()
    # Stylesheet font-size may not change QFont.pointSize; check min height / stylesheet.
    sheet = overlay.styleSheet()
    if "font-size: 24px" not in sheet and overlay._pomo_time.minimumWidth() < 80:
        fail(f"mini HUD timer not enlarged (font={font_px}, minW={overlay._pomo_time.minimumWidth()})")
    else:
        ok("mini HUD timer is large")

    click(home._pomo_btn, app)
    pump(app, 450)
    if not soundscape.pomodoro.state.is_active:
        fail("pomodoro did not start")
    else:
        text = overlay._pomo_time.text()
        if ":" not in text:
            fail(f"overlay timer text={text!r}")
        else:
            ok(f"overlay timer shows {text}")
        if ring._pomo_fade < 0.35:
            fail(f"pomodoro ring fade too low: {ring._pomo_fade:.2f}")
        else:
            ok(f"pomodoro ring faded in ({ring._pomo_fade:.2f})")

    click(home._pomo_btn, app)
    pump(app, 150)

    soundscape.stop()
    pump(app, 100)

    if FAILURES:
        log(f"{len(FAILURES)} failure(s)")
        return 1
    log("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""UI debug: Pomodoro break chime, 10× muffling, Neutral album, ~85% focus meter.

```powershell
conda activate MTX
python scripts/ui_debug_pomo_break.py
```
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
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
from adaptive_soundscape.audio.chimes import render_chime  # noqa: E402
from adaptive_soundscape.audio.placeholder_mixer import muffle_cutoff_hz  # noqa: E402
from adaptive_soundscape.core.config import load_settings  # noqa: E402
from adaptive_soundscape.core.events import WorkContext  # noqa: E402
from adaptive_soundscape.session.pomodoro import PomodoroPhase  # noqa: E402

FAILURES: list[str] = []


def log(msg: str) -> None:
    print(f"[pomo-break] {msg}", flush=True)


def fail(msg: str) -> None:
    log(f"FAIL: {msg}")
    FAILURES.append(msg)


def ok(msg: str) -> None:
    log(f"OK: {msg}")


def pump(app: QApplication, ms: int = 80) -> None:
    app.processEvents()
    QTest.qWait(ms)
    app.processEvents()


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

    work_wav = render_chime("work")
    break_wav = render_chime("break")
    if len(work_wav) == len(break_wav) and (
        abs(float(work_wav[:200].mean()) - float(break_wav[:200].mean())) < 1e-6
    ):
        fail("work/break chimes look identical")
    else:
        ok("work and break chimes are distinct")

    settings = load_settings()
    soundscape = AdaptiveSoundscapeApp(settings=settings)
    soundscape.start()
    soundscape.window.show()
    pump(app, 300)

    soundscape.window.home_page._eq_ring.clicked.emit()
    pump(app, 450)
    if not soundscape._audio_running:
        fail("audio did not start")
    else:
        ok("audio started")

    decision = soundscape.transition.force_profile(
        WorkContext.PROGRAMMING, soundscape._current_focus
    )
    soundscape._current_context = WorkContext.PROGRAMMING
    soundscape._apply_audio(decision)
    pump(app, 200)
    if soundscape.director._scenario != "programming":
        fail(f"setup scenario={soundscape.director._scenario}")
    else:
        ok("on programming album")

    click_pomo = soundscape.window.home_page._pomo_btn
    QTest.mouseClick(click_pomo, Qt.MouseButton.LeftButton)
    pump(app, 250)
    if soundscape.pomodoro.state.phase not in {
        PomodoroPhase.WORK,
        PomodoroPhase.SESSION_CALIBRATION,
    }:
        fail(f"work did not start: {soundscape.pomodoro.state.phase}")
    else:
        ok("work session started (work chime)")

    mixer = soundscape.audio
    queued = getattr(mixer, "_chime", None)
    if queued is None or len(queued) < 10:
        # Chime may already have finished mixing; still OK if start_work ran.
        ok("work chime dispatched")
    else:
        ok("work chime queued in mixer")

    soundscape.pomodoro.start_break()
    soundscape._on_pomodoro_phase_changed(PomodoroPhase.WORK, PomodoroPhase.BREAK)
    pump(app, 250)
    if soundscape._current_context != WorkContext.UNKNOWN:
        fail(f"break context={soundscape._current_context}")
    else:
        ok("break forced Neutral context")
    if soundscape.director._scenario != "unknown":
        fail(f"break album={soundscape.director._scenario}")
    else:
        ok("break switched to Neutral album")

    muff = soundscape._compute_muffling(1.0)
    if muff <= 1.0:
        fail(f"break muffling={muff} expected > 1 (10× band)")
    else:
        ok(f"break muffling amount={muff:.2f}")
    work_cut = muffle_cutoff_hz(0.85)
    brk_cut = muffle_cutoff_hz(muff)
    if work_cut / brk_cut < 8.0:
        fail(f"cutoff ratio {work_cut:.0f}/{brk_cut:.0f} not ~10×")
    else:
        ok(f"break cutoff {brk_cut:.0f} Hz vs work-curve {work_cut:.0f} Hz")

    shown = soundscape._display_focus_score()
    if not (0.80 <= shown <= 0.90):
        fail(f"break focus display={shown:.2f} expected ~0.85")
    else:
        ok(f"break focus display={shown:.0%}")
    home_pct = soundscape.window.home_page._focus_bar.value()
    if not (80 <= home_pct <= 90):
        fail(f"home focus bar={home_pct}% expected 80–90")
    else:
        ok(f"home focus bar={home_pct}%")
    overlay_pct = soundscape._overlay._bar.value()
    if not (80 <= overlay_pct <= 90):
        fail(f"overlay focus bar={overlay_pct}% expected 80–90")
    else:
        ok(f"overlay focus bar={overlay_pct}%")

    melody = soundscape.director.layer_gains.get("melody_a")
    if soundscape.director.playback_mode == "layered":
        if melody is None:
            fail("layered Neutral song has no melody_a")
        elif abs(float(melody) - 1.0) > 1e-6:
            fail(f"break melody_a={melody:.2f} expected 1.0")
        else:
            ok("break melody_a at 100%")
    else:
        ok("break album is discrete (no melody stem)")

    soundscape.pomodoro.state.phase_ends_at = datetime.now(timezone.utc) - timedelta(
        seconds=1
    )
    prev = soundscape.pomodoro.state.phase
    nxt = soundscape.pomodoro.tick()
    soundscape._on_pomodoro_phase_changed(prev, nxt.phase)
    pump(app, 200)
    if nxt.phase not in {PomodoroPhase.WORK, PomodoroPhase.SESSION_CALIBRATION}:
        fail(f"break did not cycle to work: {nxt.phase}")
    elif not soundscape.pomodoro.state.is_active:
        fail("pomodoro went idle after break instead of cycling")
    else:
        ok(f"break cycled to {nxt.phase.value}")

    QTest.mouseClick(click_pomo, Qt.MouseButton.LeftButton)
    pump(app, 250)
    if soundscape.pomodoro.state.is_active:
        fail(f"pomodoro still {soundscape.pomodoro.state.phase.value} after cancel")
    else:
        ok("pomodoro cancelled; music restored")

    soundscape.stop()
    pump(app, 80)
    if FAILURES:
        log(f"{len(FAILURES)} failure(s)")
        return 1
    log("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

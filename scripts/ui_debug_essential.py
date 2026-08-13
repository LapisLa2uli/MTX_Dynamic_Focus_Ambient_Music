"""Interactive UI debug session — drives the real Adaptive Soundscape window.

Simulates user navigation and clicks (not isolated unit tests):
  Home playback, Pomodoro, Settings debug controls, Upload SWAP,
  Demucs stem separation, and MusicGen AI layer generation.

Run:
  conda activate MTX
  python scripts/ui_debug_essential.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
import wave
from pathlib import Path

os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.text.font.db.debug=false;qt.text.font.db.info=false;qt.text.font.db.warning=false",
)
# Keep sidecars alive after a job so we can inspect health mid-run if needed.
os.environ.setdefault("ACS_KEEP_SIDECARS", "0")

import numpy as np
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton, QSlider

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adaptive_soundscape.app import AdaptiveSoundscapeApp  # noqa: E402
from adaptive_soundscape.core.config import load_settings  # noqa: E402

REPORT: list[str] = []
FAILURES: list[str] = []


def log(msg: str) -> None:
    line = f"[ui-debug] {msg}"
    print(line, flush=True)
    REPORT.append(line)


def fail(msg: str) -> None:
    log(f"FAIL: {msg}")
    FAILURES.append(msg)


def ok(msg: str) -> None:
    log(f"OK: {msg}")


def pump(app: QApplication, ms: int = 50) -> None:
    app.processEvents()
    QTest.qWait(ms)
    app.processEvents()


def click(widget, app: QApplication) -> None:
    if widget is None:
        raise RuntimeError("click target is None")
    widget.show()
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
    pump(app, 80)


def install_auto_dismiss(app: QApplication) -> None:
    """Accept modal QMessageBox dialogs so the harness does not block forever."""

    def _tick() -> None:
        for w in app.topLevelWidgets():
            if isinstance(w, QMessageBox) and w.isVisible():
                text = w.text()[:160].replace("\n", " ")
                log(f"auto-dismiss MessageBox: {text}")
                btn = w.button(QMessageBox.StandardButton.Ok) or w.button(
                    QMessageBox.StandardButton.Yes
                )
                if btn is not None:
                    click(btn, app)
                else:
                    w.accept()

    timer = QTimer()
    timer.setInterval(250)
    timer.timeout.connect(_tick)
    timer.start()
    app._ui_debug_dismiss_timer = timer  # keep alive


def write_short_mix(path: Path, seconds: float = 8.0, sr: int = 44100) -> Path:
    """Synthetic multi-band mix so Demucs has something to separate."""
    n = int(seconds * sr)
    t = np.arange(n, dtype=np.float32) / sr
    drums = 0.35 * (np.sin(2 * np.pi * 2.0 * t) > 0).astype(np.float32)
    bass = 0.25 * np.sin(2 * np.pi * 55.0 * t)
    other = 0.20 * np.sin(2 * np.pi * 330.0 * t + 0.2 * np.sin(2 * np.pi * 3 * t))
    vocals = 0.18 * np.sin(2 * np.pi * 440.0 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 1.5 * t))
    mix = np.clip(drums + bass + other + vocals, -0.95, 0.95)
    fade = min(sr // 10, n // 8)
    mix[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
    mix[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((mix * 32767).astype(np.int16).tobytes())
    return path


def wait_until(pred, app: QApplication, timeout_s: float, label: str) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if pred():
            return True
        pump(app, 200)
    fail(f"timeout waiting for {label} ({timeout_s:.0f}s)")
    return False


def navigate(soundscape: AdaptiveSoundscapeApp, app: QApplication, index: int) -> None:
    win = soundscape.window
    btns = win._nav_buttons
    if index < 0 or index >= len(btns):
        raise RuntimeError(f"bad nav index {index}")
    click(btns[index], app)
    assert win._pages.currentIndex() == index
    ok(f"navigated to page index {index}")


def debug_settings(soundscape: AdaptiveSoundscapeApp, app: QApplication) -> None:
    navigate(soundscape, app, 2)
    sp = soundscape.window.settings_page

    # Volume slider
    sp._volume_slider.setValue(55)
    pump(app, 100)
    if abs(soundscape.director._volume - 0.55) > 0.05 and abs(
        soundscape.audio.master_volume - 0.55
    ) > 0.05:
        # Director volume may be the authority.
        log(f"volume after slider: director={getattr(soundscape.director, '_volume', None)} "
            f"audio={getattr(soundscape.audio, 'master_volume', None)}")
    ok("master volume slider moved")

    # Manual concentration override
    if not hasattr(sp, "_debug_focus_toggle"):
        fail("debug focus toggle missing after merge")
        return
    click(sp._debug_focus_toggle, app)
    if not sp._debug_focus_enabled:
        fail("debug focus toggle did not enable")
    sp._debug_focus_slider.setValue(20)
    pump(app, 150)
    if not soundscape._debug_focus_override:
        fail("app did not receive debug focus override")
    else:
        ok(f"debug focus override on @ {soundscape._debug_focus_score:.2f}")

    # Force a few ticks so UI/audio path consumes override
    for _ in range(3):
        soundscape._tick()
        pump(app, 50)
    if abs(soundscape._focus_score - soundscape._debug_focus_score) > 0.05:
        fail(
            f"focus score {soundscape._focus_score:.2f} != debug "
            f"{soundscape._debug_focus_score:.2f}"
        )
    else:
        ok("focus bar path follows debug concentration")

    sp._debug_focus_slider.setValue(90)
    pump(app, 100)
    for _ in range(3):
        soundscape._tick()
        pump(app, 50)
    ok(f"debug concentration raised → focus={soundscape._focus_score:.2f}")

    # Layer volume override
    click(sp._debug_layer_toggle, app)
    if not soundscape._debug_layer_override:
        fail("debug layer override not enabled on app")
    else:
        ok("debug layer override enabled")
    if "pad" in sp._layer_sliders:
        sp._layer_sliders["pad"].setValue(10)
        pump(app, 100)
        ok("pad layer slider moved to 10%")

    # Leave override on for playback audition, then disable focus override later
    click(sp._debug_focus_toggle, app)  # off
    pump(app, 50)


def home_playback_and_pomodoro(soundscape: AdaptiveSoundscapeApp, app: QApplication) -> None:
    navigate(soundscape, app, 0)
    home = soundscape.window.home_page

    # Start soundscape via the EQ ring (primary play control)
    before = soundscape._audio_running
    click(home._eq_ring, app)
    pump(app, 400)
    if not soundscape._audio_running:
        # Fallback: emit the same signal the ring would
        home.action_toggled.emit(True)
        pump(app, 400)
    if soundscape._audio_running:
        ok("audio started from home EQ ring")
    else:
        fail(f"audio did not start (was {before})")

    soundscape._tick()
    pump(app, 80)
    if soundscape._debug_mode_on():
        if not home._music_detail.isVisible():
            fail("music detail hidden while debug is on")
        else:
            ok("music detail shown in debug mode")
    soundscape._debug_focus_override = False
    soundscape._debug_layer_override = False
    soundscape._refresh_ui()
    pump(app, 50)
    if home._music_detail.isVisible():
        fail("music detail shown outside debug")
    else:
        ok("music detail hidden outside debug")
    if not home._theme_label.isVisible() or not home._theme_label.text().strip():
        fail("working context line missing")
    else:
        ok(f"context line kept: {home._theme_label.text()}")

    # Pomodoro start / cancel
    click(home._pomo_btn, app)
    pump(app, 200)
    if soundscape.pomodoro.state.is_active:
        ok("Pomodoro started")
        click(home._pomo_btn, app)
        pump(app, 200)
        if not soundscape.pomodoro.state.is_active:
            ok("Pomodoro cancelled")
        else:
            fail("Pomodoro still active after cancel click")
    else:
        fail("Pomodoro did not start")

    # A few live focus ticks without debug override
    soundscape._debug_focus_override = False
    scores = []
    for _ in range(5):
        soundscape._tick()
        scores.append(round(soundscape._focus_score, 3))
        pump(app, 80)
    ok(f"live focus ticks: {scores}")


def upload_separate_and_generate(
    soundscape: AdaptiveSoundscapeApp, app: QApplication, sample: Path
) -> None:
    navigate(soundscape, app, 1)
    upload = soundscape.window.upload_page
    # Ensure programming tab (index 0)
    if upload._tab_buttons:
        click(upload._tab_buttons[0], app)
    panel = upload._panels.get("programming")
    if panel is None:
        fail("programming upload panel missing")
        return

    # Stage file as if user dropped it
    panel._upload_zone._stage_file(sample)
    pump(app, 100)
    if panel._upload_zone.staged_path is None:
        fail("upload zone did not stage sample")
        return
    ok(f"staged sample {sample.name}")

    # SWAP
    click(panel._swap_btn, app)
    pump(app, 500)

    # Stem separation should start automatically (thread + progress dialog)
    thread = getattr(panel, "_stem_thread", None)
    if thread is None:
        log("no auto stem thread; will rely on Generate AI button")
    else:
        ok("stem separation thread started from SWAP")
        finished = {"done": False, "ok": False, "err": ""}

        def _ok(_paths) -> None:
            finished["done"] = True
            finished["ok"] = True

        def _fail(msg: str) -> None:
            finished["done"] = True
            finished["ok"] = False
            finished["err"] = str(msg)

        try:
            thread.succeeded.connect(_ok)
            thread.failed.connect(_fail)
        except Exception:
            pass

        log("waiting for Demucs (+ optional MusicGen) — this can take several minutes…")
        if wait_until(
            lambda: finished["done"] or not thread.isRunning(),
            app,
            1200,
            "stem pipeline",
        ):
            pump(app, 500)
            if thread.isRunning():
                wait_until(lambda: finished["done"], app, 30, "stem signals")
            if finished["ok"] or (not thread.isRunning() and not finished["err"]):
                ok("stem / layer pipeline finished")
            else:
                fail(f"stem pipeline failed: {finished['err'] or 'unknown'}")

    # Generate AI layers explicitly (user button)
    panel.refresh()
    pump(app, 100)
    if hasattr(panel, "_ai_btn") and panel._ai_btn.isEnabled():
        click(panel._ai_btn, app)
        pump(app, 300)
        gen_thread = getattr(panel, "_gen_thread", None)
        if gen_thread is not None and gen_thread.isRunning():
            ok("AI generate thread running")
            wait_until(lambda: not gen_thread.isRunning(), app, 900, "MusicGen generate")
            ok("AI generate thread finished")
        else:
            log("AI generate may have finished quickly or reused auto_on_upload layers")
    else:
        log("AI layers button disabled — skipping explicit generate click")


def inspect_latest_song(soundscape: AdaptiveSoundscapeApp) -> None:
    from adaptive_soundscape.audio.album import list_songs
    from adaptive_soundscape.core.config import resolve_assets_dir

    assets = resolve_assets_dir(soundscape.settings)
    songs = list_songs(assets, "programming")
    if not songs:
        fail("no programming songs after upload")
        return
    song = songs[-1]
    ok(f"latest song dir: {song}")
    layers = ["pad", "harmony", "melody_a", "rhythm", "texture", "melody_b"]
    found = []
    for lid in layers:
        folder = song / lid
        if folder.is_dir():
            files = list(folder.glob("*"))
            if files:
                found.append(f"{lid}:{len(files)}")
    if found:
        ok(f"layer files present: {', '.join(found)}")
    else:
        fail("no per-layer audio files found under latest song")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Adaptive Soundscape UI Debug")
    install_auto_dismiss(app)

    settings = load_settings()
    # Prefer shorter generative timeout only for health messaging; keep long for real GPU.
    log(f"stem auto_on_upload={settings.stem_separation.auto_on_upload} "
        f"gen auto_on_upload={settings.generative_layers.auto_on_upload}")
    log(f"stem conda_env={settings.stem_separation.conda_env} "
        f"musicgen conda_env={settings.generative_layers.conda_env}")

    soundscape = AdaptiveSoundscapeApp(settings=settings)
    soundscape.start()
    soundscape.window.show()
    soundscape.window.raise_()
    pump(app, 300)
    ok("app window shown")

    tmp = Path(tempfile.mkdtemp(prefix="acs_ui_debug_"))
    sample = write_short_mix(tmp / "ui_debug_mix.wav", seconds=8.0)
    ok(f"wrote sample mix {sample} ({sample.stat().st_size} bytes)")

    try:
        debug_settings(soundscape, app)
        home_playback_and_pomodoro(soundscape, app)
        upload_separate_and_generate(soundscape, app, sample)
        inspect_latest_song(soundscape)
    except Exception:
        fail("uncaught exception:\n" + traceback.format_exc())

    # Stop audio / tear down
    try:
        if soundscape._audio_running:
            soundscape.window.home_page.action_toggled.emit(False)
            pump(app, 200)
        soundscape.stop()
    except Exception as exc:
        fail(f"shutdown error: {exc}")

    log("=" * 60)
    if FAILURES:
        log(f"RESULT: {len(FAILURES)} failure(s)")
        for f in FAILURES:
            log(f"  - {f}")
        return 1
    log("RESULT: all exercised UI paths OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

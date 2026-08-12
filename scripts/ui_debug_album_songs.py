"""UI debug: Manage Albums lists MusicGen-generated songs.

Expects at least one ``*_gen_*`` song under assets (run
``scripts/generate_album_songs.py`` first).

```powershell
conda activate MTX
python scripts/ui_debug_album_songs.py
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
from adaptive_soundscape.audio.music_manifest import song_dirs  # noqa: E402
from adaptive_soundscape.core.config import load_settings, resolve_assets_dir  # noqa: E402
from adaptive_soundscape.ui.album_manager import AlbumManagerDialog  # noqa: E402

FAILURES: list[str] = []


def log(msg: str) -> None:
    print(f"[album-ui] {msg}", flush=True)


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
    assets = resolve_assets_dir(settings)
    gen_songs = [
        p
        for sc in sorted({d.name for d in assets.iterdir() if d.is_dir()})
        for p in song_dirs(assets, sc)
        if "_gen_" in p.name
    ]
    if not gen_songs:
        fail("no *_gen_* songs found — run generate_album_songs.py first")
        return 1
    ok(f"found {len(gen_songs)} generated song(s) on disk")
    target = gen_songs[0]
    scenario = target.parent.name
    ok(f"target {scenario}/{target.name}")

    soundscape = AdaptiveSoundscapeApp(settings=settings)
    soundscape.start()
    soundscape.window.show()
    pump(app, 300)

    click(soundscape.window._nav_buttons[1], app)
    ok("nav → upload")

    dlg = AlbumManagerDialog(assets, parent=soundscape.window)
    dlg.show()
    pump(app, 250)

    # Switch to the scenario tab that owns the generated song
    profile_ids = getattr(dlg, "_tab_ids", {})
    for idx, pid in profile_ids.items():
        if pid == scenario:
            dlg._switch_tab(idx)
            pump(app, 200)
            break
    ok(f"album tab → {scenario}")

    tab = dlg._tabs.get(scenario)
    if tab is None:
        fail(f"missing album tab for {scenario}")
    else:
        if hasattr(tab, "refresh_songs"):
            tab.refresh_songs()
            pump(app, 150)
        song_combo = getattr(tab, "_song_combo", None)
        if song_combo is None:
            fail("album tab missing song combo")
        else:
            labels = [song_combo.itemText(i) for i in range(song_combo.count())]
            data = [str(song_combo.itemData(i) or "") for i in range(song_combo.count())]
            if any(target.name in t for t in labels) or any(
                target.name in d for d in data
            ):
                ok(f"Manage Albums lists {target.name}")
            else:
                fail(f"{target.name} not in song combo: {labels[:12]}")

    if (target / "manifest.json").is_file():
        ok("generated song has manifest.json")
    else:
        fail("missing manifest.json")

    dlg.close()
    soundscape.stop()
    pump(app, 100)

    if FAILURES:
        log(f"{len(FAILURES)} failure(s)")
        return 1
    log("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

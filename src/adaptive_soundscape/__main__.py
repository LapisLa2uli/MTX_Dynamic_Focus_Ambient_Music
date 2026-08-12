"""Entry point: python -m adaptive_soundscape"""

from __future__ import annotations

import os
import sys

# Silence noisy Qt font-database warnings ("OpenType support missing for ...",
# script 11) that are printed to the console on Windows font fallback paths.
os.environ.setdefault(
    "QT_LOGGING_RULES",
    "qt.text.font.db.debug=false;qt.text.font.db.info=false;qt.text.font.db.warning=false",
)

from PyQt6.QtWidgets import QApplication

from adaptive_soundscape.app import AdaptiveSoundscapeApp


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Adaptive Soundscape")
    soundscape = AdaptiveSoundscapeApp()
    soundscape.start()
    exit_code = app.exec()
    soundscape.stop()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

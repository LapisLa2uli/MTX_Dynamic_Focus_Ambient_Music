"""Entry point: python -m adaptive_soundscape"""

from __future__ import annotations

import sys

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

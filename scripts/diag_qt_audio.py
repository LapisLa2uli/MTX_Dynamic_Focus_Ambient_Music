"""Test sounddevice playback inside PyQt6 event loop."""
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from adaptive_soundscape.core.config import resolve_assets_dir, load_settings
from adaptive_soundscape.audio.placeholder_mixer import PlaceholderMixer


def main() -> None:
    app = QApplication(sys.argv)
    settings = load_settings()
    assets = resolve_assets_dir(settings)
    mixer = PlaceholderMixer(assets_dir=assets, master_volume=0.8)
    mixer.start(profile_id="programming")
    print("playing:", mixer.is_playing, flush=True)

    def stop() -> None:
        mixer.stop()
        app.quit()

    QTimer.singleShot(3000, stop)
    app.exec()
    print("done", flush=True)


if __name__ == "__main__":
    main()

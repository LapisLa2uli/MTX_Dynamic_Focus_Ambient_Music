"""Verify all project dependencies import from the active environment."""

from __future__ import annotations

import importlib
import sys

MODULES = [
    "PyQt6",
    "PyQt6.QtWidgets",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "win32gui",
    "win32process",
    "pynput",
    "pynput.keyboard",
    "pynput.mouse",
    "psutil",
    "sounddevice",
    "numpy",
    "scipy",
    "scipy.signal",
    "pydantic",
    "pydantic_settings",
    "yaml",
    "cffi",
    "adaptive_soundscape",
    "adaptive_soundscape.app",
]

USER_SITE = "AppData\\Roaming\\Python"


def main() -> int:
    failed: list[str] = []
    leaked: list[str] = []

    print(f"Python: {sys.executable}")
    print(f"Prefix: {sys.prefix}")
    print()

    for name in MODULES:
        try:
            mod = importlib.import_module(name)
            path = getattr(mod, "__file__", str(mod))
            status = "OK"
            if USER_SITE.lower() in path.replace("/", "\\").lower():
                status = "LEAK"
                leaked.append(f"{name} -> {path}")
            print(f"{status:4} {name}")
        except Exception as exc:
            print(f"FAIL {name}: {exc}")
            failed.append(name)

    print()
    if failed:
        print("Missing/failed:", ", ".join(failed))
    if leaked:
        print("Loaded from user site-packages (should be in MTX):")
        for line in leaked:
            print(f"  {line}")

    return 1 if failed or leaked else 0


if __name__ == "__main__":
    raise SystemExit(main())

# Adaptive Cognitive Soundscape (Phase 1 MVP)

Context-aware ambient audio that adapts to your work context and estimated cognitive state. Runs locally on **Windows** with privacy-first, metadata-only monitoring.

The app watches what you are doing (process names, window titles, input cadence—not keystroke content), classifies your work context, estimates focus, and crossfades between pre-made soundscapes.

---

## Requirements

| Component | Required? | Notes |
|-----------|-----------|-------|
| **Windows 10/11** | Yes | Activity monitoring uses pywin32 + pynput |
| **Python 3.10+** | Yes | Recommended: Conda env `MTX` |
| **Conda or Miniconda** | Recommended | Keeps dependencies isolated |
| **Working audio output** | Yes | Uses your Windows default playback device |
| **Godot 4.x** | Optional | Only if `audio.backend: godot` in config |

---

## Installation

### 1. Install Conda (if needed)

Download and install [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or Anaconda, then open **Anaconda Prompt** or PowerShell.

### 2. Clone or open this project

```powershell
cd "D:\stuff\Adaptive Focus Music System"
```

### 3. Create the Python environment

```powershell
conda create -n MTX python=3.10 -y
conda activate MTX
```

### 4. Install Python packages

Install into the conda env (not user site-packages):

```powershell
pip install --no-user -r requirements.txt -e .
```

Or with dev tools (pytest):

```powershell
pip install --no-user -e ".[dev]"
```

**What gets installed**

| Package | Purpose |
|---------|---------|
| `PyQt6` | Desktop UI |
| `pywin32` | Active window / process detection |
| `pynput` | Keyboard & mouse **event counts** (not key content) |
| `psutil` | CPU load |
| `sounddevice` | Default audio playback (placeholder backend) |
| `numpy`, `scipy` | Audio mixing & pad generation |
| `miniaudio` | MP3 decoding |
| `pydantic`, `pydantic-settings`, `PyYAML` | Configuration |
| `pytest` | Tests (also in `requirements.txt`) |

### 5. Verify the install

```powershell
conda activate MTX
python scripts/verify_imports.py
```

You should see `OK` for every module and exit code `0`. If any package shows `LEAK`, it was loaded from user site-packages—reinstall with `pip install --no-user`.

### 6. (Optional) Install Godot 4 for the Godot audio backend

The **default** config uses the built-in Python mixer and does **not** require Godot. Install Godot only if you want four-layer stem mixing via a sidecar process.

1. Download **Godot 4.2+** (Standard, not .NET): [godotengine.org/download](https://godotengine.org/download)
2. Extract the ZIP. On Windows you get `Godot_v4.x-stable_win64.exe`.
3. Point the app at it using **one** of:
   - **Config file** — edit `config/default.yaml`:
     ```yaml
     audio:
       backend: godot
       godot_executable: "D:/path/to/Godot_v4.6.3-stable_win64.exe"
     ```
   - **Environment variable** — in PowerShell before launching:
     ```powershell
     $env:GODOT4 = "D:\path\to\Godot_v4.6.3-stable_win64.exe"
     ```
   - **PATH** — add the Godot folder to your system `PATH` so `godot` runs from any terminal.

If Godot fails to start, leave `fallback_to_placeholder: true` (default) and the app will use the built-in mixer instead.

---

## Audio assets

Place sound files in `assets/audio/`. Supported formats: **`.mp3`**, **`.wav`** (and `.ogg` in Godot only).

### Profile file names

Each work context maps to a profile ID:

| Context | File stem |
|---------|-----------|
| Programming | `programming` |
| Team / workflow | `team_workflow` |
| Reading / writing | `reading_writing` |
| Scientific | `scientific` |
| Creative / design | `creative_design` |
| Distraction recovery | `distraction` |
| Unknown / neutral | `unknown` |

**Flat layout (default, recommended)**

```
assets/audio/
  programming.mp3          # main loop
  programming_pad.wav      # softer underlayer (optional)
  reading_writing.mp3
  ...
```

With `prefer_mp3: true` (default), the app plays your **MP3** files instead of auto-generated synthetic WAV placeholders.

**Layered layout (Godot, optional)**

```
assets/audio/
  programming/
    ambient.wav
    rhythm.wav
    harmonic.wav
    accent.wav
```

See [`godot/README.md`](godot/README.md) for the Godot sidecar API and stem details.

### Generate placeholder tones (optional)

If you have no music files yet, the app can create simple synthetic loops:

```powershell
conda activate MTX
python scripts/generate_audio_assets.py       # mains + pads (skip existing)
python scripts/generate_pad_assets.py           # pads only
python scripts/generate_pad_assets.py --force   # regenerate all pads
```

---

## Run the app

```powershell
conda activate MTX
cd "D:\stuff\Adaptive Focus Music System"
python -m adaptive_soundscape
```

Or, after install:

```powershell
adaptive-soundscape
```

---

## How to use the app

1. **Launch** the app (see above). A dark dashboard window opens.
2. **Check your context** — the **Context**, **Focus State**, and **Active Profile** cards update about once per second based on what you are doing.
3. **Click Start Audio** — playback begins for the current context profile (e.g. `programming` while coding). Click again to stop.
4. **Adjust sensitivity** — the **Sensitivity** spinner (0.2–2.0) scales how strongly keyboard/mouse activity affects the focus score.
5. **Manual override** — enable **Manual override** and pick a context from the dropdown to force a specific soundscape regardless of detected activity.
6. **Privacy** — toggle collection of window titles, process names, or activity logging. Logging is **off** by default.

### Status line

If something goes wrong, a red message appears at the bottom (e.g. missing audio files, Godot port in use). When Godot is unavailable and the built-in mixer takes over, you may see: *“Using built-in audio mixer (Godot unavailable).”*

### Tips

- Ensure Windows **Sound → Output** is set to the device you are listening on (headphones, speakers, etc.).
- If you hear nothing, check the status line, confirm files exist in `assets/audio/`, and try raising `master_volume` in `config/default.yaml`.
- Close stray **Godot** windows if you switched backends or see port **8765** errors.

---

## Configuration

Edit [`config/default.yaml`](config/default.yaml):

```yaml
audio:
  backend: placeholder          # placeholder (default) or godot
  master_volume: 0.75
  prefer_mp3: true              # use your .mp3 files over synthetic .wav
  fallback_to_placeholder: true # if godot fails, use built-in mixer
  assets_dir: assets/audio
  godot_executable: ""          # path to Godot 4.x exe (godot backend only)
  godot_port: 8765

context:
  default_dwell_seconds: 45     # seconds before context label changes

transition:
  deep_focus_crossfade_seconds: 12.0
  distraction_recovery_seconds: 4.5
  cooldown_seconds: 60.0

cognitive:
  sensitivity: 1.0
  focus_smoothing: 0.85

privacy:
  collect_window_titles: true
  collect_process_names: true
  log_activity: false             # off by default
```

Environment overrides use the prefix `ACS_` (e.g. `ACS_AUDIO__MASTER_VOLUME=0.8`).

---

## Audio backends

| Backend | Config value | How it works |
|---------|--------------|--------------|
| **Placeholder mixer** (default) | `placeholder` | Python + `sounddevice`; mixes main + pad MP3/WAV in-process |
| **Godot sidecar** | `godot` | Separate Godot process; TCP JSON on `127.0.0.1:8765`; supports four-layer stems |

Both backends share the same `AudioBackend` interface (start/stop, crossfade, brightness/energy/warmth parameters).

---

## Tests

```powershell
conda activate MTX
pytest
```

---

## Architecture

Five subsystems wired via an in-process event bus (~1 Hz):

1. **Activity Monitor** — active window (pywin32), input cadence counts (pynput), CPU (psutil)
2. **Context Classifier** — rule-based labels with dwell-time hysteresis
3. **Cognitive State Estimator** — focus score (0–1) and discrete states
4. **Adaptive Music Engine** — placeholder mixer (default) or Godot 4 sidecar
5. **Transition Controller** — crossfades, cooldown, hysteresis

---

## Paper

Report sources: [`paper/main.tex`](paper/main.tex). Update §2.2 when changing architecture or audio backend (see `.cursor/rules/paper-sync.mdc`).

---

## Privacy

- All processing is **local only** — no network calls for monitoring or audio
- Input tracking records **event counts only**, never keystroke text
- Window titles and process names can be disabled in the UI
- Activity logging is **disabled by default**

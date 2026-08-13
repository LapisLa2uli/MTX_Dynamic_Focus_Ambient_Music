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
| **Godot 4.x** | Optional | Not in repo (gitignored); download and place in project root if using `audio.backend: godot` |

---

## Installation

### 1. Install Conda (if needed)

Download and install [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or Anaconda, then open **Anaconda Prompt** or PowerShell.

### 2. Clone or open this project

```powershell
cd "D:\stuff\MTX\Adaptive Focus Music System"
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

You should see `OK` for every module and exit code `0`. If any package shows `LEAK`, it was loaded from user site-packages—reinstall with `pip install --no-user`, or temporarily set `$env:PYTHONNOUSERSITE = "1"`.

**PyQt6 note:** This project pins `PyQt6==6.8.1` (see `requirements.txt`). `PyQt6` 6.11.x can fail on some Windows/conda setups with `DLL load failed … 找不到指定的程序` when importing `QtCore`/`QtWidgets`. If that happens, reinstall from `requirements.txt`. Do **not** install conda `qt6-main` / `matplotlib` into the `MTX` env alongside pip PyQt6—they conflict on DLL search paths.

### 6. (Optional) Install Godot 4 for the Godot audio backend

The **default** config uses the built-in Python mixer and does **not** require Godot. Install Godot only if you want four-layer stem mixing via a sidecar process.

**The Godot executable is not in this repository** — it is listed in `.gitignore` (`Godot_v4.6.3-stable_win64.exe`). After cloning, you must download and place it yourself.

#### Download

1. Go to [godotengine.org/download](https://godotengine.org/download)
2. Download **Godot 4.2+**, **Standard** edition (not .NET)
3. Extract the ZIP — on Windows you get a single file such as `Godot_v4.6.3-stable_win64.exe`

#### Where to put it

Copy the executable into the **project root** (same folder as `README.md` and `config/`):

```
Adaptive Focus Music System/
  Godot_v4.6.3-stable_win64.exe   ← place here
  README.md
  config/
  godot/
  src/
  ...
```

You can use a different Godot 4.x version, but then update both the filename and `godot_executable` in config to match.

#### Configure the app

Edit [`config/default.yaml`](config/default.yaml):

```yaml
audio:
  backend: godot                    # switch from placeholder to godot
  godot_executable: "D:/stuff/MTX/Adaptive Focus Music System/Godot_v4.6.3-stable_win64.exe"
  godot_project: godot
  godot_port: 8765
  fallback_to_placeholder: true     # use built-in mixer if Godot fails
```

Use **forward slashes** in the path (works on Windows). Replace `D:/stuff/MTX/Adaptive Focus Music System` with the absolute path to **your** clone of this repo.

Example if your project lives at `C:\Users\You\Projects\Adaptive Focus Music System`:

```yaml
  godot_executable: "C:/Users/You/Projects/Adaptive Focus Music System/Godot_v4.6.3-stable_win64.exe"
```

Leave `backend: placeholder` if you do not install Godot — the app works without it.

**Alternatives to editing the config file**

- Environment variable (PowerShell, current session):
  ```powershell
  $env:GODOT4 = "D:\stuff\MTX\Adaptive Focus Music System\Godot_v4.6.3-stable_win64.exe"
  ```
- Add Godot’s folder to your system `PATH` (then `godot_executable` can stay empty if `godot` is found automatically)

If Godot fails to start, leave `fallback_to_placeholder: true` and the app will use the built-in mixer instead.

---

## Adaptive music (layered stems + discrete fallback)

Music adapts in two nested levels:

1. **Work scenario** selects a scenario **album**, then a random **song family**.
2. **Default (layered):** compatible stem loops (`pad`, `harmony`, `melody_a`, `rhythm`, optional `melody_b` / `texture` / `recovery`) play together. `MusicDirector` maps `focus_score` → **per-layer volumes** (with slew + energy limiting).
3. **Fallback (discrete):** if a song has fewer than two base layers, the older calm / focus / deep_focus **file switching** path is used.

The authoritative concentration signal is the **Focus Likelihood Index (FLI)** mapped to `focus_score` ∈ `[0, 1]`. Uncalibrated sessions use the default **A/S/I** weighted metric only; after calibration, probe (P) and gated pattern assist apply. Focus falls faster than it rises (asymmetric EMA). When smoothed focus stays below `cognitive.auto_distraction_enter` for a few seconds, the app switches the **UI/music** context to Distraction/recovery (classification for scoring still uses the real app category). See [`src/adaptive_soundscape/focus_index/README.md`](src/adaptive_soundscape/focus_index/README.md). Low focus also drives **music muffling** (low-pass) scaled by Settings → Muffling Strength × `muffling.curve_multiplier`.

### Thresholds & mix (`config/default.yaml` → `adaptive_music`)

| Setting | Default | Meaning |
|---------|---------|---------|
| `enter_focus` / `leave_focus` | 0.40 / 0.30 | UI / discrete Focus band |
| `enter_deep_focus` / `leave_deep_focus` | 0.70 / 0.60 | UI / discrete Deep Focus band |
| `min_state_seconds` | 3.0 | Debounce for discrete swaps / label |
| `gain_slew_seconds` | 1.25 | Layer gain ramp time |
| `energy_limit` | 1.35 | Soft cap on summed layer gains |
| `intensity_smoothing` | 0.70 | Extra EMA for music decisions only |

### Asset layout + manifest

```
assets/audio/
  programming/
    programming_01/
      manifest.json
      pad/pad_01.wav
      harmony/harmony_01.wav
      melody_a/melody_a_01.wav
      rhythm/rhythm_01.wav
      melody_b/                 # optional MusicGen
      texture/                 # optional MusicGen
      calm/ focus/ deep_focus/ # discrete fallback
```

Set `"playbackMode": "layered"` (default when ≥2 base layers exist) or `"discrete"`.

Migrate / refresh layered stubs (identical full-mix copies — not real stems):

```powershell
conda activate MTX
cd "D:\stuff\MTX\Adaptive Focus Music System"
python scripts/migrate_albums.py
```

### Self-hosted Demucs (stem separation)

Base layers (`pad` / `harmony` / `melody_a` / `rhythm`) are produced by a **separate FastAPI Demucs sidecar** (not the MTX env). Startup never runs Demucs; it only installs cheap stub copies until you separate.

```powershell
conda create -n demucs python=3.10 -y
conda activate demucs
cd "D:\stuff\MTX\Adaptive Focus Music System\services\demucs_api"
pip install -r requirements.txt
.\run.ps1
```

Stub mode (no model download): `$env:DEMUCS_STUB = "1"; .\run.ps1`

Then from MTX, separate existing album songs:

```powershell
conda activate MTX
python scripts/separate_album_stems.py
python scripts/separate_album_stems.py --scenario programming --song programming_01
python scripts/separate_album_stems.py --force
```

**Manage Albums → Upload as New Song** also auto-separates when `stem_separation.auto_on_upload` is true and the sidecar is online. Uploading into a single existing stem layer does not re-run Demucs.

Stem map: `drums→rhythm`, `bass→pad`, `other→harmony`, `vocals→melody_a` (high-passed `other` if vocals are near-silent). Config: `stem_separation` in `config/default.yaml` (`api_base_url: http://127.0.0.1:7863`, default model `htdemucs_ft`). Sidecars stay warm when `sidecar_apis.stop_when_done: false`.

### Self-hosted MusicGen (offline layer generation)

Intensity layers are generated by a **separate FastAPI sidecar** (not the MTX env):

```powershell
conda create -n musicgen python=3.10 -y
conda activate musicgen
cd "D:\stuff\MTX\Adaptive Focus Music System\services\musicgen_api"
pip install -r requirements.txt
.\run.ps1
```

Stub mode (no GPU / no model download): `$env:MUSICGEN_STUB = "1"; .\run.ps1`

Then from MTX:

```powershell
conda activate MTX
python scripts/generate_intensity_layers.py --scenario programming --song programming_01
```

Or use **Manage Albums → Generate AI Layers**. Config: `generative_layers` in `config/default.yaml` (`api_base_url: http://127.0.0.1:7862`). Generation never runs on the 1 Hz tick.

### UI controls

- **Start Audio** — glass EQ-ring on Home (scales with window; capped on fullscreen so session buttons stay visible). A **mini HUD** stays on top (top-right, draggable/resizable) with play/stop, focus, and Pomodoro.
- **Music State** — Calm / Focus / Deep Focus (+ mode, song, top layer gains).
- **Pomodoro / Calibrate** — home session chips. While a Pomodoro runs, a diminishing countdown arc sits **between the glass button and the waveform**.
- **Upload** — SWAP a mix into a scenario album; auto Demucs + optional MusicGen layers.
- **Settings → Effect response** — muffling aggressiveness (1×–5×), music intensity lag, layer blend time, focus bar lag, **context blend time** (equal-power crossfade when switching work soundscapes). Live-adjustable and saved to `config/user_ui_settings.json`.
- **Settings → Debug** — manual concentration override; manual layer volumes (sliders appear only when enabled).
- **Manage Albums** — advanced stem / AI controls.

### UI debug harness

Drive the real window (navigation, debug sliders, SWAP, Demucs, MusicGen) without clicking by hand:

```powershell
conda activate MTX
python scripts/ui_debug_essential.py
python scripts/ui_debug_focus_distraction.py   # auto-distraction path
python scripts/ui_debug_effects.py             # Effect response sliders
python scripts/ui_debug_album_songs.py         # Manage Albums lists generated songs
python scripts/ui_debug_transition.py          # context blend + scenario switch
python scripts/ui_debug_overlay_pomo.py        # mini HUD + Pomodoro ring
```

### Generate placeholder tones (optional)

If an album is empty, the app synthesizes a simple loop and migrates it into a song family with layered stubs on startup.

### Fill albums with MusicGen songs

With the MusicGen sidecar available (GPU or `MUSICGEN_STUB=1`):

```powershell
conda activate MTX
python scripts/generate_album_songs.py --scenario programming --count 2
# Seed only (skip Demucs / AI layers):
python scripts/generate_album_songs.py --scenario creative_design --count 1 --no-separate --no-ai-layers
```

Generated WAVs live under `assets/audio/` (gitignored). Re-run the script after changing prompts to replace `*_gen_*` song folders.

MusicGen song seeds use per-scenario briefs (tempo, instrumentation, and “avoid” lists) aligned with the Focus Music Requirements notes — `build_song_prompt` in `src/adaptive_soundscape/audio/prompt_builder.py` (programming 70 BPM, team workflow 76, reading 62, scientific 68, creative 72).

---

## Run the app

```powershell
conda activate MTX
cd "D:\stuff\MTX\Adaptive Focus Music System"
python -m adaptive_soundscape
```

Or, after install:

```powershell
adaptive-soundscape
```

### One-click demo ZIP (portable package)

Yes — you can ship the project **together with the Python environment** in a single zip so recipients do not need Conda or `pip install`.

**Build the zip** (on a Windows machine with Conda installed):

```powershell
cd "D:\stuff\MTX\Adaptive Focus Music System"
powershell -ExecutionPolicy Bypass -File scripts\build_demo_package.ps1
```

The script creates a fresh `acs-demo-pack` conda env from `requirements.txt`, packs it with [conda-pack](https://conda.github.io/conda-pack/), bundles **Godot 4** for layered audio, and zips everything. Output: **`dist/AdaptiveSoundscape-Demo-win64.zip`** (~540 MB with Godot + audio assets).

**Before building:** place a Godot 4 Standard Windows exe in the project root (e.g. `Godot_v4.6.3-stable_win64.exe` from [godotengine.org/download](https://godotengine.org/download)). The build script copies it into the zip as `Godot.exe`. Or pass an explicit path: `-GodotExe "D:\path\to\Godot.exe"`.

| Included | Notes |
|----------|-------|
| `runtime/` | Portable Python env (`conda-pack` of `acs-demo-pack`) |
| `Godot.exe` | Godot 4 sidecar — four-layer adaptive audio (final product) |
| `src/`, `config/`, `assets/`, `godot/` | Application code and audio assets |
| `run_demo.bat` | **Single command to launch the demo** |

**Run the demo** (recipient, no install step):

1. Unzip anywhere on Windows 10/11.
2. Double-click **`run_demo.bat`** (or run it from a terminal).

The first launch runs `conda-unpack` once to fix paths. The demo uses the **Godot audio backend** by default (same layered mixing as a full install). If Godot fails to start, the app falls back to the built-in placeholder mixer.

**Limitations**

- Built for **Windows x64 only** (matches pywin32 / this project’s target platform).
- The zip must be built on a machine with Conda and a local Godot exe; rebuild after dependency changes.
- Antivirus software may flag packed Python runtimes; signing or whitelisting may be needed in some environments.

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
  godot_project: godot
  godot_executable: ""          # required for godot backend — see "Install Godot" above
  godot_port: 8765

context:
  default_dwell_seconds: 5     # seconds before context label changes

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

When using the Godot backend, set `backend: godot` and point `godot_executable` at the exe in the **project root** (gitignored — not included in the repo):

```yaml
  backend: godot
  godot_executable: "D:/stuff/MTX/Adaptive Focus Music System/Godot_v4.6.3-stable_win64.exe"
```

Replace the path with the absolute path to your clone. Use forward slashes on Windows.

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
- FLI stores only **app categories**, durations, switches, idle intervals, probe aggregates, and calibration pattern vectors in `config/focus_index.sqlite` (gitignored; 7-day retention). Export/delete from Settings. No titles, URLs, key contents, clipboard, screenshots, mic, or camera.

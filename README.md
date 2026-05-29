# Adaptive Cognitive Soundscape (Phase 1 MVP)

Context-aware ambient audio that adapts to your work context and estimated cognitive state. Runs locally on Windows with privacy-first metadata-only monitoring.

## Setup

```bash
conda create -n MTX python=3.10 -y
conda activate MTX
pip install --no-user -r requirements.txt -e .
```

Or via `pyproject.toml`:

```bash
conda activate MTX
pip install --no-user -e ".[dev]"
```

Use `--no-user` so packages install into the MTX env instead of your user site-packages.

Verify dependencies:

```bash
conda activate MTX
python scripts/verify_imports.py
```

## Run

```bash
conda activate MTX
python -m adaptive_soundscape
```

Generate placeholder audio loops manually (optional — auto-generated on first run):

```bash
python scripts/generate_audio_assets.py
```

## Tests

```bash
conda activate MTX
pytest
```

## Architecture

Five subsystems wired via an in-process event bus:

1. **Activity Monitor** — active window (pywin32), input cadence counts (pynput), CPU (psutil)
2. **Context Classifier** — rule-based labels with dwell-time hysteresis
3. **Cognitive State Estimator** — probabilistic focus score (0–1) and discrete states
4. **Adaptive Music Engine** — placeholder sounddevice/numpy mixer (`AudioBackend` protocol for future FMOD)
5. **Transition Controller** — gradual crossfades, cooldown, hysteresis

## Privacy

- All processing is **local only** — no network calls
- Input tracking records **event counts only**, never keystroke text
- Window titles and process names can be disabled in the UI
- Activity logging is **disabled by default** (`config/default.yaml`)

## Configuration

Edit `config/default.yaml` for dwell times, crossfade durations, sensitivity, and audio settings.

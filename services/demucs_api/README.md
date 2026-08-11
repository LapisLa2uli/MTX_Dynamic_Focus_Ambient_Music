# Demucs API sidecar

Self-hosted [Demucs](https://github.com/facebookresearch/demucs) (`htdemucs`) HTTP service that splits a full mix into `drums` / `bass` / `other` / `vocals` stems for Adaptive Soundscape base layers.

**Do not install these dependencies into the MTX / PyQt conda env.**

## Setup

```powershell
conda create -n demucs python=3.10 -y
conda activate demucs
cd "D:\stuff\MTX\Adaptive Focus Music System\services\demucs_api"
pip install -r requirements.txt
```

GPU strongly recommended.

## Run

```powershell
.\run.ps1
```

Stub mode (no model download, synthetic distinct tones — for wiring tests):

```powershell
$env:DEMUCS_STUB = "1"
.\run.ps1
```

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Model loaded / device |
| POST | `/v1/separate` | Separate a mix (`audio_base64` → `stems.{drums,bass,other,vocals}`) |

The Adaptive Soundscape app calls this from **Manage Albums** (auto on new full-mix upload) or `scripts/separate_album_stems.py`, never from the 1 Hz focus tick.

## Stem → layer map (app-side)

| Demucs stem | App layer |
|-------------|-----------|
| drums | `rhythm` |
| bass | `pad` |
| other | `harmony` |
| vocals | `melody_a` (high-passed `other` if near-silent) |

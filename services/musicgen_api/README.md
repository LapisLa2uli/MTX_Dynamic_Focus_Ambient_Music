# MusicGen API sidecar

Self-hosted [Meta MusicGen](https://huggingface.co/facebook/musicgen-small) HTTP service for offline intensity-layer generation.

**Do not install these dependencies into the MTX / PyQt conda env.**

## Setup

```powershell
conda create -n musicgen python=3.10 -y
conda activate musicgen
cd "D:\stuff\MTX\Adaptive Focus Music System\services\musicgen_api"
pip install -r requirements.txt
```

GPU strongly recommended for `facebook/musicgen-small`.

## Run

```powershell
.\run.ps1
```

Stub mode (no model download, synthetic WAV — for wiring tests):

```powershell
$env:MUSICGEN_STUB = "1"
.\run.ps1
```

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Model loaded / device |
| POST | `/v1/generate_layer` | Generate a WAV layer (`audio_base64`) |

The Adaptive Soundscape app calls this only from **Manage Albums → Generate AI layers** or `scripts/generate_intensity_layers.py`, never from the 1 Hz focus tick.

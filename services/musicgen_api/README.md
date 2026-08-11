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

Install a **CUDA** PyTorch wheel (default `pip install torch` often pulls a CPU build).
Also start with `PYTHONNOUSERSITE=1` (set by `run.ps1`) so a user-site CPU torch
under `%APPDATA%\Python` cannot shadow the conda env:

```powershell
conda activate musicgen
pip install --upgrade torch --index-url https://download.pytorch.org/whl/cu124
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

## Run

```powershell
.\run.ps1
```

`run.ps1` defaults to `MUSICGEN_DEVICE=cuda` and uses `model_cache\local_musicgen_small`
when present (offline). Override with `$env:MUSICGEN_DEVICE = "cpu"` only for debugging.
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

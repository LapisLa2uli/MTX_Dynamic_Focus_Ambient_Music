# Start the MusicGen FastAPI sidecar on http://127.0.0.1:7862
# Use a dedicated env (NOT MTX / PyQt). Example:
#   conda create -n musicgen python=3.10 -y
#   conda activate musicgen
#   pip install -r requirements.txt
#   pip install --upgrade torch --index-url https://download.pytorch.org/whl/cu124
#
# For a no-GPU smoke test without downloading weights:
#   $env:MUSICGEN_STUB = "1"

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Prefer the conda env's packages over a CPU-only torch in %APPDATA%\Python.
$env:PYTHONNOUSERSITE = "1"

if (-not $env:MUSICGEN_MODEL_SIZE) {
    $env:MUSICGEN_MODEL_SIZE = "small"
}
if (-not $env:MUSICGEN_DEVICE) {
    $env:MUSICGEN_DEVICE = "cuda"
}
if (-not $env:MUSICGEN_MODEL_PATH) {
    $local = Join-Path $PSScriptRoot "model_cache\local_musicgen_small"
    if (Test-Path $local) {
        $env:MUSICGEN_MODEL_PATH = $local
        $env:HF_HUB_OFFLINE = "1"
        $env:TRANSFORMERS_OFFLINE = "1"
    }
}

Write-Host "Starting MusicGen API on http://127.0.0.1:7862 (model=$env:MUSICGEN_MODEL_SIZE device=$env:MUSICGEN_DEVICE stub=$env:MUSICGEN_STUB)"
python -m uvicorn app:app --host 127.0.0.1 --port 7862

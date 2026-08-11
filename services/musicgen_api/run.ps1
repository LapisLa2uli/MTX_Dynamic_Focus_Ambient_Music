# Start the MusicGen FastAPI sidecar on http://127.0.0.1:7862
# Use a dedicated env (NOT MTX / PyQt). Example:
#   conda create -n musicgen python=3.10 -y
#   conda activate musicgen
#   pip install -r requirements.txt
#
# For a no-GPU smoke test without downloading weights:
#   $env:MUSICGEN_STUB = "1"

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $env:MUSICGEN_MODEL_SIZE) {
    $env:MUSICGEN_MODEL_SIZE = "small"
}

Write-Host "Starting MusicGen API on http://127.0.0.1:7862 (model=$env:MUSICGEN_MODEL_SIZE stub=$env:MUSICGEN_STUB)"
python -m uvicorn app:app --host 127.0.0.1 --port 7862

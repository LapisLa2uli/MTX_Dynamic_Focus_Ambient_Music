# Start the Demucs FastAPI sidecar on http://127.0.0.1:7863
# Use a dedicated env (NOT MTX / PyQt). Example:
#   conda create -n demucs python=3.10 -y
#   conda activate demucs
#   pip install -r requirements.txt
# Or reuse the musicgen env (has torch+demucs on this machine).
#
# For a no-GPU smoke test without downloading weights:
#   $env:DEMUCS_STUB = "1"

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Prefer the conda env's packages over a CPU-only torch in %APPDATA%\Python.
$env:PYTHONNOUSERSITE = "1"

if (-not $env:DEMUCS_MODEL) {
    $env:DEMUCS_MODEL = "htdemucs"
}
if (-not $env:DEMUCS_DEVICE) {
    $env:DEMUCS_DEVICE = "cuda"
}

Write-Host "Starting Demucs API on http://127.0.0.1:7863 (model=$env:DEMUCS_MODEL device=$env:DEMUCS_DEVICE stub=$env:DEMUCS_STUB)"
python -m uvicorn app:app --host 127.0.0.1 --port 7863

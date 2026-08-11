# Start the Demucs FastAPI sidecar on http://127.0.0.1:7863
# Use a dedicated env (NOT MTX / PyQt). Example:
#   conda create -n demucs python=3.10 -y
#   conda activate demucs
#   pip install -r requirements.txt
#
# For a no-GPU smoke test without downloading weights:
#   $env:DEMUCS_STUB = "1"

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $env:DEMUCS_MODEL) {
    $env:DEMUCS_MODEL = "htdemucs"
}

Write-Host "Starting Demucs API on http://127.0.0.1:7863 (model=$env:DEMUCS_MODEL stub=$env:DEMUCS_STUB)"
python -m uvicorn app:app --host 127.0.0.1 --port 7863

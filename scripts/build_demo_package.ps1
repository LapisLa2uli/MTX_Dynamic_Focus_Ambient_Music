# Build a self-contained Windows demo ZIP (project + portable conda env + Godot).
#
# Creates a fresh conda env from requirements.txt, packs it with conda-pack,
# bundles Godot 4 for layered audio, and zips everything with run_demo.bat.
#
# Output: dist/AdaptiveSoundscape-Demo-win64.zip
#
# Usage (from project root):
#   powershell -ExecutionPolicy Bypass -File scripts\build_demo_package.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\build_demo_package.ps1 -GodotExe "D:\path\to\Godot_v4.6.3-stable_win64.exe"

param(
    [string]$GodotExe = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DistRoot = Join-Path $ProjectRoot "dist"
$StageRoot = Join-Path $DistRoot "AdaptiveSoundscape-Demo"
$RuntimeArchive = Join-Path $DistRoot "acs-runtime.tar.gz"
$ZipPath = Join-Path $DistRoot "AdaptiveSoundscape-Demo-win64.zip"
$PackEnv = "acs-demo-pack"
$BundledGodotName = "Godot.exe"

function Find-GodotExecutable {
    param([string]$ExplicitPath)
    if ($ExplicitPath -ne "" -and (Test-Path $ExplicitPath)) {
        return (Resolve-Path $ExplicitPath).Path
    }
    $patterns = @(
        "Godot_v4*.exe",
        "Godot*.exe"
    )
    foreach ($pattern in $patterns) {
        $match = Get-ChildItem -Path $ProjectRoot -Filter $pattern -File -ErrorAction SilentlyContinue |
            Sort-Object Name |
            Select-Object -First 1
        if ($match) {
            return $match.FullName
        }
    }
    throw @"
Godot executable not found in project root.

Download Godot 4.x Standard from https://godotengine.org/download
Place it in:
  $ProjectRoot

Expected name like Godot_v4.6.3-stable_win64.exe
Or pass -GodotExe `"D:\path\to\Godot.exe`"
"@
}

function Ensure-CondaPack {
    $listJson = & conda run -n base conda list -f conda-pack --json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $listJson) {
        Write-Host "Installing conda-pack into base environment..."
        & conda install -n base -c conda-forge conda-pack -y
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install conda-pack. Run: conda install -n base -c conda-forge conda-pack"
        }
    }
}

function Reset-PackEnv {
    Write-Host "==> Preparing clean conda env '$PackEnv'..."
    try { & conda env remove -n $PackEnv -y 2>&1 | Out-Null } catch { }
    & conda create -n $PackEnv python=3.10 pip -y
    if ($LASTEXITCODE -ne 0) { throw "conda create failed" }

    Write-Host "==> Installing dependencies into '$PackEnv'..."
    & conda run -n $PackEnv pip install --no-user -r (Join-Path $ProjectRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

    Write-Host "==> Verifying imports..."
    $env:PYTHONNOUSERSITE = "1"
    & conda run -n $PackEnv python -c "import sys; sys.path.insert(0, r'$ProjectRoot\src'); import adaptive_soundscape; import PyQt6; import sounddevice"
    if ($LASTEXITCODE -ne 0) { throw "Import verification failed; fix requirements before packaging" }
}

function Write-DemoConfig {
    param([string]$TargetPath)
    $sourceConfig = Join-Path $ProjectRoot "config\default.yaml"
    if (-not (Test-Path $sourceConfig)) {
        throw "Missing config/default.yaml"
    }
    $content = Get-Content $sourceConfig -Raw
    $content = $content -replace "(?m)^(\s*)backend:\s*placeholder\s*$", '${1}backend: godot'
    $content = $content -replace "(?m)^(\s*)godot_executable:.*$", '${1}godot_executable: "Godot.exe"'
    Set-Content -Path $TargetPath -Value $content -Encoding UTF8
}

$GodotSource = Find-GodotExecutable -ExplicitPath $GodotExe
Write-Host "==> Using Godot: $GodotSource"

Write-Host "==> Checking prerequisites..."
Ensure-CondaPack
Reset-PackEnv

Write-Host "==> Packing conda env '$PackEnv' (may take a few minutes)..."
New-Item -ItemType Directory -Force -Path $DistRoot | Out-Null
if (Test-Path $RuntimeArchive) { Remove-Item $RuntimeArchive -Force }

& conda pack -n $PackEnv -o $RuntimeArchive
if ($LASTEXITCODE -ne 0) {
    throw "conda pack failed"
}

Write-Host "==> Staging demo folder..."
if (Test-Path $StageRoot) { Remove-Item $StageRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null

$IncludeDirs = @("src", "assets", "godot")
foreach ($dir in $IncludeDirs) {
    $source = Join-Path $ProjectRoot $dir
    if (Test-Path $source) {
        Copy-Item $source (Join-Path $StageRoot $dir) -Recurse -Force
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $StageRoot "config") | Out-Null
Write-DemoConfig -TargetPath (Join-Path $StageRoot "config\default.yaml")

$IncludeFiles = @("run_demo.bat", "requirements.txt", "pyproject.toml", "README.md")
foreach ($file in $IncludeFiles) {
    $source = Join-Path $ProjectRoot $file
    if (Test-Path $source) {
        Copy-Item $source (Join-Path $StageRoot $file) -Force
    }
}

Write-Host "==> Bundling Godot as $BundledGodotName ..."
Copy-Item $GodotSource (Join-Path $StageRoot $BundledGodotName) -Force
$godotMb = [math]::Round((Get-Item (Join-Path $StageRoot $BundledGodotName)).Length / 1MB, 1)
Write-Host "    Godot size: $godotMb MB"

Write-Host "==> Extracting portable runtime..."
$RuntimeDir = Join-Path $StageRoot "runtime"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
& tar -xzf $RuntimeArchive -C $RuntimeDir
if ($LASTEXITCODE -ne 0) { throw "Failed to extract runtime archive" }

@'
Adaptive Cognitive Soundscape — Demo Package
==========================================

Quick start (Windows):
  1. Unzip this folder anywhere.
  2. Double-click run_demo.bat

First launch runs conda-unpack once to fix paths (a few seconds).

This bundle includes:
  - Portable Python runtime (no install required)
  - Godot.exe (layered adaptive audio engine)
  - Your MP3/WAV soundscape assets

Audio uses the Godot sidecar by default (four-layer stem mixing).
If Godot fails to start, the app falls back to the built-in mixer.

'@ | Set-Content -Path (Join-Path $StageRoot "DEMO.txt") -Encoding UTF8

Write-Host "==> Creating ZIP (this may take several minutes)..."
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $StageRoot "*") -DestinationPath $ZipPath -Force

$sizeMb = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
Write-Host ""
Write-Host "Done: $ZipPath ($sizeMb MB)"
Write-Host "Recipients: unzip, then double-click run_demo.bat"

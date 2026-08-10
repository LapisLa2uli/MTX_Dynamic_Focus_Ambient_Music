@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "RUNTIME=%~dp0runtime"
set "PYTHON=%RUNTIME%\python.exe"
set "GODOT_EXE=%~dp0Godot.exe"

if not exist "%PYTHON%" (
    echo [ERROR] Portable Python runtime not found at:
    echo   %PYTHON%
    echo.
    echo Unzip the full demo package or rebuild it with:
    echo   powershell -ExecutionPolicy Bypass -File scripts\build_demo_package.ps1
    exit /b 1
)

if not exist "%RUNTIME%\.unpack_done" (
    echo First run: fixing portable environment paths...
    if exist "%RUNTIME%\Scripts\conda-unpack.exe" (
        "%RUNTIME%\Scripts\conda-unpack.exe"
    ) else if exist "%RUNTIME%\conda-unpack.exe" (
        "%RUNTIME%\conda-unpack.exe"
    )
    echo.>"%RUNTIME%\.unpack_done"
)

set "PYTHONNOUSERSITE=1"
set "PYTHONPATH=%~dp0src"
set "ACS_AUDIO__FALLBACK_TO_PLACEHOLDER=true"

if exist "%GODOT_EXE%" (
    set "ACS_AUDIO__BACKEND=godot"
    set "ACS_AUDIO__GODOT_EXECUTABLE=%GODOT_EXE%"
    echo Starting Adaptive Cognitive Soundscape ^(Godot audio^)...
) else (
    set "ACS_AUDIO__BACKEND=placeholder"
    echo [WARN] Godot.exe not found; using built-in placeholder audio.
    echo Starting Adaptive Cognitive Soundscape...
)

"%PYTHON%" -m adaptive_soundscape
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
    echo.
    echo Demo exited with error code %EXITCODE%.
    pause
)
exit /b %EXITCODE%

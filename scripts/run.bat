@echo off
setlocal
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
    echo [x] Python 3.10+ was not found in PATH.
    echo     Install it from https://www.python.org/downloads/ and tick "Add to PATH".
    pause
    exit /b 1
)

python -c "import PIL, numpy" >nul 2>nul
if errorlevel 1 (
    echo [*] Installing dependencies ^(Pillow, numpy^)...
    python -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo [x] Dependency install failed.
        pause
        exit /b 1
    )
)

echo [*] Starting NaiWa Mouse from source...
start "" pythonw app.py
echo [ok] Running. Ctrl+Alt+Q to quit, Ctrl+Alt+S to show/hide.
timeout /t 3 >nul

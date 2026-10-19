@echo off
setlocal
cd /d "%~dp0"
echo [*] Restoring the system cursor...
if exist "NaiWaMouse.exe" (
    start /wait "" "NaiWaMouse.exe" --restore-cursor
) else if exist "NaiWaMouse\NaiWaMouse.exe" (
    start /wait "" "NaiWaMouse\NaiWaMouse.exe" --restore-cursor
) else (
    echo [!] NaiWaMouse.exe not found next to this file.
    pause
    exit /b 1
)
echo [ok] 光标已恢复
timeout /t 2 >nul

@echo off
setlocal
cd /d "%~dp0.."

rem Prefer the packaged exe: it restores cursors without needing Python.
set "RESTORE="
if exist "dist\NaiWaMouse\NaiWaMouse.exe" set "RESTORE=dist\NaiWaMouse\NaiWaMouse.exe"
if not defined RESTORE if exist "dist\NaiWaMouse.exe" set "RESTORE=dist\NaiWaMouse.exe"

if defined RESTORE (
    start /wait "" "%RESTORE%" --restore-cursor
) else (
    python -m naiwa --restore-cursor 2>nul
    if errorlevel 1 (
        powershell -NoProfile -Command "Add-Type -Namespace W -Name N -MemberDefinition '[DllImport(\"user32.dll\")] public static extern bool SystemParametersInfo(uint a, uint b, IntPtr c, uint d);'; [W.N]::SystemParametersInfo(0x57, 0, [IntPtr]::Zero, 2) | Out-Null"
    )
)

echo [ok] System cursor restored.
timeout /t 2 >nul

@echo off
setlocal
cd /d "%~dp0.."

echo [*] Stopping NaiWa Mouse...
taskkill /IM NaiWaMouse.exe /F >nul 2>nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe'\" | Where-Object { $_.CommandLine -like '*app.py*' -or $_.CommandLine -like '*naiwa*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [*] Restoring the system cursor...
call "%~dp0restore_cursor.bat"

echo [ok] Done.
timeout /t 2 >nul

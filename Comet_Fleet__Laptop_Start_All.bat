@echo off
if /i "%~1" NEQ "--hidden" (
    powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Process -FilePath $env:ComSpec -ArgumentList '/c ""%~f0"" --hidden' -WindowStyle Hidden"
    exit /b
)

title Comet Fleet - Laptop Start All
cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

python -c "import pyvda" >nul 2>nul
if errorlevel 1 (
    python -m pip install --disable-pip-version-check pyvda >nul 2>nul
)

start "Comet Browser Layout Watcher" /min powershell -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -Command "cd '%~dp0'; python .\browser_window_watcher.py 2>&1 | Tee-Object -FilePath .\browser_window_watcher_log.txt -Append"

start "Comet Fleet - Sync Client" /min powershell -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -Command "cd '%~dp0'; python .\sync_updates_to_main.py --loop --interval 60 2>&1 | Tee-Object -FilePath .\sync_client_log.txt -Append"

timeout /t 2 /nobreak >nul

start "Comet Fleet - Dashboard Backlog" powershell -NoProfile -ExecutionPolicy Bypass -Command "cd '%~dp0'; python .\start_dashboard.py 2>&1 | Tee-Object -FilePath .\dashboard_log.txt -Append"

timeout /t 2 /nobreak >nul

start "Comet Fleet - Device Command Worker" /min powershell -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -Command "cd '%~dp0'; python .\device_command_worker.py 2>&1 | Tee-Object -FilePath .\device_command_worker_log.txt -Append"

exit /b 0

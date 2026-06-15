$ErrorActionPreference = "Continue"

$Project = "C:\Users\excel\Desktop\Comet_Fleet_HQ"
Set-Location $Project

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " COMET FLEET - EMERGENCY REPAIR LAPTOP" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "Restoring safe working laptop files..." -ForegroundColor Yellow

$Required = @(
    ".\start_dashboard_SAFE_WORKING_NOW.py",
    ".\mobile_worker_SAFE_WORKING_NOW.py",
    ".\device_command_worker_SAFE_WORKING_NOW.py",
    ".\ui\app_SAFE_WORKING_NOW.js",
    ".\ui\style_SAFE_WORKING_NOW.css",
    ".\ui\index_SAFE_WORKING_NOW.html"
)

foreach ($File in $Required) {
    if (-not (Test-Path $File)) {
        Write-Host "[FAILED] Missing safe backup: $File" -ForegroundColor Red
        Read-Host "Press ENTER to close"
        exit 1
    }
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"

Copy-Item ".\start_dashboard.py" ".\start_dashboard_BEFORE_EMERGENCY_REPAIR_$Stamp.py" -Force
Copy-Item ".\mobile_worker.py" ".\mobile_worker_BEFORE_EMERGENCY_REPAIR_$Stamp.py" -Force
Copy-Item ".\device_command_worker.py" ".\device_command_worker_BEFORE_EMERGENCY_REPAIR_$Stamp.py" -Force
Copy-Item ".\ui\app.js" ".\ui\app_BEFORE_EMERGENCY_REPAIR_$Stamp.js" -Force
Copy-Item ".\ui\style.css" ".\ui\style_BEFORE_EMERGENCY_REPAIR_$Stamp.css" -Force
Copy-Item ".\ui\index.html" ".\ui\index_BEFORE_EMERGENCY_REPAIR_$Stamp.html" -Force

Copy-Item ".\start_dashboard_SAFE_WORKING_NOW.py" ".\start_dashboard.py" -Force
Copy-Item ".\mobile_worker_SAFE_WORKING_NOW.py" ".\mobile_worker.py" -Force
Copy-Item ".\device_command_worker_SAFE_WORKING_NOW.py" ".\device_command_worker.py" -Force
Copy-Item ".\ui\app_SAFE_WORKING_NOW.js" ".\ui\app.js" -Force
Copy-Item ".\ui\style_SAFE_WORKING_NOW.css" ".\ui\style.css" -Force
Copy-Item ".\ui\index_SAFE_WORKING_NOW.html" ".\ui\index.html" -Force

Write-Host "[OK] Restored laptop dashboard, mobile worker, and command worker files." -ForegroundColor Green

Write-Host ""
Write-Host "Checking Python syntax..." -ForegroundColor Yellow

python -m py_compile ".\start_dashboard.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAILED] start_dashboard.py has a Python error." -ForegroundColor Red
    Read-Host "Press ENTER to close"
    exit 1
}

python -m py_compile ".\mobile_worker.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAILED] mobile_worker.py has a Python error." -ForegroundColor Red
    Read-Host "Press ENTER to close"
    exit 1
}

python -m py_compile ".\device_command_worker.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAILED] device_command_worker.py has a Python error." -ForegroundColor Red
    Read-Host "Press ENTER to close"
    exit 1
}

Write-Host "[OK] Python files compile." -ForegroundColor Green

Write-Host ""
Write-Host "Testing main PC coordinator connection..." -ForegroundColor Yellow

$MainOk = $false

try {
    $Health = Invoke-RestMethod "http://100.68.214.2:9555/api/health" -TimeoutSec 5
    if ($Health.ok -eq $true) {
        $MainOk = $true
    }
} catch {
    $MainOk = $false
}

if ($MainOk) {
    Write-Host "[OK] Main PC coordinator is reachable." -ForegroundColor Green
} else {
    Write-Host "[WARN] Main PC coordinator is NOT reachable from laptop." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Starting laptop dashboard..." -ForegroundColor Yellow

Start-Process powershell.exe -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "cd `"$Project`"; python .\start_dashboard.py 2>&1 | Tee-Object -FilePath .\dashboard_log.txt -Append"
)

Start-Sleep -Seconds 2

Write-Host "Starting mobile worker..." -ForegroundColor Yellow

Start-Process powershell.exe -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "cd `"$Project`"; python .\mobile_worker.py 2>&1 | Tee-Object -FilePath .\mobile_worker_log.txt -Append"
)

Start-Sleep -Seconds 2

Write-Host "Starting device command worker..." -ForegroundColor Yellow

Start-Process powershell.exe -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-Command",
    "cd `"$Project`"; python .\device_command_worker.py 2>&1 | Tee-Object -FilePath .\device_command_worker_log.txt -Append"
)

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " LAPTOP EMERGENCY REPAIR COMPLETE" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host "Restored and started:" -ForegroundColor Green
Write-Host "- Laptop Dashboard" -ForegroundColor Green
Write-Host "- Mobile Worker" -ForegroundColor Green
Write-Host "- Device Command Worker" -ForegroundColor Green
Write-Host ""
Read-Host "Press ENTER to close"

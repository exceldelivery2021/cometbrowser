# Create desktop shortcuts for Comet Fleet - Laptop/Dashboard PC
# Run this on the LAPTOP user: excel

$ProjectDir = "C:\Users\excel\Desktop\Comet_Fleet_HQ"
$Desktop = [Environment]::GetFolderPath("Desktop")
$WshShell = New-Object -ComObject WScript.Shell

function New-Shortcut {
    param(
        [string]$Name,
        [string]$Target,
        [string]$WorkingDir,
        [string]$Description,
        [int]$IconIndex = 44
    )

    if (!(Test-Path $Target)) {
        Write-Host "[ERROR] Missing target: $Target" -ForegroundColor Red
        return
    }

    $ShortcutPath = Join-Path $Desktop $Name
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Target
    $Shortcut.WorkingDirectory = $WorkingDir
    $Shortcut.Description = $Description
    $Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,$IconIndex"
    $Shortcut.Save()

    Write-Host "[OK] Created shortcut: $ShortcutPath" -ForegroundColor Green
}

New-Shortcut `
    -Name "Comet Fleet - Start All.lnk" `
    -Target (Join-Path $ProjectDir "START_LAPTOP_ALL.bat") `
    -WorkingDir $ProjectDir `
    -Description "Syncs updates to main PC, opens dashboard, and starts mobile worker" `
    -IconIndex 44

New-Shortcut `
    -Name "Comet Fleet - Dashboard Only.lnk" `
    -Target (Join-Path $ProjectDir "START_DASHBOARD_MASTER.bat") `
    -WorkingDir $ProjectDir `
    -Description "Syncs updates and opens only the dashboard" `
    -IconIndex 13

New-Shortcut `
    -Name "Comet Fleet - Mobile Worker.lnk" `
    -Target (Join-Path $ProjectDir "START_MOBILE_WORKER_MASTER.bat") `
    -WorkingDir $ProjectDir `
    -Description "Starts the fake/mobile worker heartbeat and task runner" `
    -IconIndex 220

Write-Host ""
Write-Host "Laptop desktop shortcut setup complete." -ForegroundColor Green
pause

$ErrorActionPreference = 'SilentlyContinue'

$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$rootDir = Split-Path -Parent $scriptsDir
$launcherPath = Join-Path $scriptsDir 'launch_asr_gui.pyw'
$watchdogPath = Join-Path $scriptsDir 'watch_asr.ps1'
$pythonExe = Join-Path $rootDir 'venv\Scripts\python.exe'
$pythonwExe = Join-Path $rootDir 'venv\Scripts\pythonw.exe'

Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe' OR Name = 'powershell.exe'" |
  Where-Object {
    ($_.ExecutablePath -eq $pythonExe -or $_.ExecutablePath -eq $pythonwExe -or $_.Name -eq 'powershell.exe') -and (
      ($_.CommandLine -like '*asr_app*') -or
      ($_.CommandLine -like "*$launcherPath*") -or
      ($_.CommandLine -like "*$watchdogPath*")
    )
  } |
  ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
    Write-Output ("Stopped PID " + $_.ProcessId + " | " + $_.Name)
  }

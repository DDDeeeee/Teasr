$ErrorActionPreference = 'Stop'

$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$rootDir = Split-Path -Parent $scriptsDir
$runtimeDir = Join-Path $rootDir 'runtime'
$srcDir = Join-Path $rootDir 'src'
$launcherPath = Join-Path $scriptsDir 'launch_asr_gui.pyw'
$pythonw = Join-Path $rootDir 'venv\Scripts\pythonw.exe'
$stdout = Join-Path $runtimeDir 'asr_stdout.log'
$stderr = Join-Path $runtimeDir 'asr_stderr.log'

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
Set-Location $rootDir

if (-not (Test-Path $launcherPath)) {
  throw "Missing GUI launcher: $launcherPath"
}
if (-not (Test-Path $pythonw)) {
  throw "Missing pythonw.exe: $pythonw"
}

if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
  $env:PYTHONPATH = $srcDir
} else {
  $env:PYTHONPATH = "$srcDir;$($env:PYTHONPATH)"
}

Start-Process -FilePath $pythonw -ArgumentList @($launcherPath, '--minimized') -WorkingDirectory $rootDir -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr | Out-Null

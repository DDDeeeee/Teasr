param(
  [int]$CheckSeconds = 5,
  [int]$RestartDelaySeconds = 2
)

$ErrorActionPreference = 'Stop'

$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$rootDir = Split-Path -Parent $scriptsDir
$runtimeDir = Join-Path $rootDir 'runtime'
$srcDir = Join-Path $rootDir 'src'
$entryModulePath = Join-Path $srcDir 'asr_app\__main__.py'

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
Set-Location $rootDir

$venvPython = Join-Path $rootDir 'venv\Scripts\python.exe'
$venvPythonw = Join-Path $rootDir 'venv\Scripts\pythonw.exe'
$moduleName = 'asr_app'
$guiLauncher = Join-Path $rootDir 'scripts\launch_asr_gui.pyw'

$pidFile = Join-Path $runtimeDir 'asr_watchdog_asr_pid.txt'
$logFile = Join-Path $runtimeDir 'asr_watchdog.log'
$asrStdout = Join-Path $runtimeDir 'asr_stdout.log'
$asrStderr = Join-Path $runtimeDir 'asr_stderr.log'

function Write-Log([string]$Message) {
  $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
  Add-Content -Path $logFile -Value $line -Encoding UTF8
}
$mutex = New-Object System.Threading.Mutex($false, 'Local\ASR_WATCHDOG_MUTEX')
if (-not $mutex.WaitOne(0)) {
  Write-Log '[INFO] Watchdog already running; exiting.'
  exit 0
}

if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
  $env:PYTHONPATH = $srcDir
} else {
  $env:PYTHONPATH = "$srcDir;$($env:PYTHONPATH)"
}

function Get-AsrProcessByPidFile {
  if (-not (Test-Path $pidFile)) { return $null }
  try {
    $pid = (Get-Content -Path $pidFile -ErrorAction Stop | Select-Object -First 1).Trim()
    if (-not $pid) { return $null }
    return Get-Process -Id ([int]$pid) -ErrorAction Stop
  } catch {
    return $null
  }
}

function Find-AsrProcess {
  $filters = "Name = 'python.exe' OR Name = 'pythonw.exe'"
  $procs = Get-CimInstance Win32_Process -Filter $filters -ErrorAction SilentlyContinue
  foreach ($p in $procs) {
    $exePath = $p.ExecutablePath
    $commandLine = $p.CommandLine
    if (-not $exePath) { continue }
    $matchesRuntime = ($exePath -eq $venvPython) -or ($exePath -eq $venvPythonw)
    if (-not $matchesRuntime) { continue }
    $matchesApp = $false
    if ($commandLine) {
      $matchesApp = $commandLine.Contains('-m asr_app') -or $commandLine.Contains($guiLauncher)
    }
    if (-not $matchesApp) { continue }
    try {
      return Get-Process -Id $p.ProcessId -ErrorAction Stop
    } catch {
    }
  }
  return $null
}
function Start-Asr {
  if (-not (Test-Path $entryModulePath)) {
    Write-Log "[ERROR] Missing module entrypoint: $entryModulePath"
    return $null
  }

  if (-not (Test-Path $venvPython)) {
    Write-Log "[ERROR] Missing venv python: $venvPython"
    return $null
  }

  try {
    $p = Start-Process -FilePath $venvPython -ArgumentList @('-u', '-m', $moduleName, '--minimized') -WorkingDirectory $rootDir -WindowStyle Hidden -RedirectStandardOutput $asrStdout -RedirectStandardError $asrStderr -PassThru
    Set-Content -Path $pidFile -Value $p.Id -Encoding ASCII
    Write-Log "[INFO] Started ASR, pid=$($p.Id)"
    return $p
  } catch {
    Write-Log "[ERROR] Failed to start ASR: $($_.Exception.Message)"
    return $null
  }
}

Write-Log '[INFO] Watchdog started.'
while ($true) {
  try {
    $asr = Get-AsrProcessByPidFile
    if (-not $asr) { $asr = Find-AsrProcess }

    if (-not $asr) {
      Write-Log '[WARN] ASR not running; restarting.'
      Start-Asr | Out-Null
      Start-Sleep -Seconds $RestartDelaySeconds
    }
  } catch {
    Write-Log "[ERROR] Watchdog loop error: $($_.Exception.Message)"
  }

  Start-Sleep -Seconds $CheckSeconds
}



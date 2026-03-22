param(
    [string]$Destination,
    [switch]$Desktop
)

$ErrorActionPreference = 'Stop'
$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$rootDir = Split-Path -Parent $scriptsDir
$launcher = Join-Path $rootDir 'scripts\launch_asr_gui.pyw'
$pythonw = Join-Path $rootDir 'venv\Scripts\pythonw.exe'
$python = Join-Path $rootDir 'venv\Scripts\python.exe'
$propertyPython = $python
$pathPython = Get-Command python.exe -ErrorAction SilentlyContinue
if ($pathPython) {
    $propertyPython = $pathPython.Source
}
$propertyWriter = Join-Path $rootDir 'scripts\set_shortcut_app_id.py'
$appId = 'ASRStudio.ASRAssistant'
$icon = Join-Path $rootDir 'ASR Assistant.ico'
if (-not (Test-Path $icon)) {
    $icon = $pythonw
}

if (-not (Test-Path $launcher)) {
    throw "Missing launcher: $launcher"
}
if (-not (Test-Path $pythonw)) {
    throw "Missing pythonw.exe: $pythonw"
}
if (-not (Test-Path $python)) {
    throw "Missing python.exe: $python"
}
if (-not (Test-Path $propertyWriter)) {
    throw "Missing shortcut property writer: $propertyWriter"
}

if ([string]::IsNullOrWhiteSpace($Destination)) {
    if ($Desktop) {
        $Destination = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ASR Assistant.lnk'
    } else {
        $Destination = Join-Path $rootDir 'ASR Assistant.lnk'
    }
}

$targetDir = Split-Path -Parent $Destination
if (-not (Test-Path $targetDir)) {
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($Destination)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"' + $launcher + '"'
$shortcut.WorkingDirectory = $rootDir
$shortcut.Description = 'Launch ASR Assistant'
if (Test-Path $icon) {
    $shortcut.IconLocation = $icon + ',0'
}
$shortcut.Save()
& $propertyPython $propertyWriter $Destination $appId
if ($LASTEXITCODE -ne 0) {
    throw "Failed to write AppUserModelID into shortcut: $Destination"
}
Write-Output $Destination

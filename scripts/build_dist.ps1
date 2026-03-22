param(
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root 'venv\Scripts\python.exe'
$specPath = Join-Path $root 'packaging\TEASR.spec'

if (-not (Test-Path $venvPython)) {
    throw "Missing venv python: $venvPython"
}

$pyinstallerArgs = @('-m', 'PyInstaller', '--noconfirm')
if ($Clean) {
    $pyinstallerArgs += '--clean'
}
$pyinstallerArgs += $specPath

Push-Location $root
try {
    & $venvPython @pyinstallerArgs
}
finally {
    Pop-Location
}

$ErrorActionPreference = 'Stop'

$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$rootDir = Split-Path -Parent $scriptsDir
$runtimeDir = Join-Path $rootDir 'runtime'
$srcDir = Join-Path $rootDir 'src'
$entryModulePath = Join-Path $srcDir 'asr_app\__main__.py'

@echo off
setlocal
chcp 65001 >nul

set "ROOT_DIR=%~dp0"
set "PYTHONW=%ROOT_DIR%venv\Scripts\pythonw.exe"
set "LAUNCHER=%ROOT_DIR%scripts\launch_asr_gui.pyw"
set "ICON_PATH=%ROOT_DIR%ASR Assistant.ico"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_DIR%\ASR Assistant.lnk"

echo ========================================
echo ASR Startup Setup
echo ========================================
echo.

echo [1/3] Checking required files...
if not exist "%PYTHONW%" (
    echo [ERROR] Missing %PYTHONW%
    pause
    exit /b 1
)
if not exist "%LAUNCHER%" (
    echo [ERROR] Missing %LAUNCHER%
    pause
    exit /b 1
)
echo [OK] Required files found.

echo.
echo [2/3] Creating startup shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT_PATH%'); $Shortcut.TargetPath = '%PYTHONW%'; $Shortcut.Arguments = '`"%LAUNCHER%`" --minimized'; $Shortcut.WorkingDirectory = '%ROOT_DIR%'; if (Test-Path '%ICON_PATH%') { $Shortcut.IconLocation = '%ICON_PATH%,0' }; $Shortcut.Description = 'Launch ASR Assistant at startup'; $Shortcut.Save();"
if %errorLevel% neq 0 (
    echo [ERROR] Failed to create startup shortcut.
    pause
    exit /b 1
)
echo [OK] Shortcut created: %SHORTCUT_PATH%

echo.
echo [3/3] Verifying setup...
if not exist "%SHORTCUT_PATH%" (
    echo [ERROR] Startup shortcut not found after creation.
    pause
    exit /b 1
)

echo [OK] Startup setup completed.
echo.
echo Startup now launches the normal GUI minimized, without watchdog.
pause

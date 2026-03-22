@echo off
setlocal
chcp 65001 >nul

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo Starting ASR service...

call "%ROOT_DIR%venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [ERROR] Failed to activate venv.
  pause
  exit /b 1
)

set "PYTHONPATH=%ROOT_DIR%src;%PYTHONPATH%"
python -m asr_app
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo [ERROR] ASR exited with code %EXIT_CODE%.
  pause
)

exit /b %EXIT_CODE%
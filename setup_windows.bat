@echo off
setlocal
cd /d "%~dp0"
if not exist "scripts\setup_windows.ps1" (
  echo [ERROR] Missing scripts\setup_windows.ps1
  pause
  exit /b 1
)
echo [INFO] Setting up isolated Python environment.
echo [INFO] Does not automatically download Ollama models or FFmpeg.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\setup_windows.ps1"
set "rc=%errorlevel%"
if not "%rc%"=="0" pause
exit /b %rc%

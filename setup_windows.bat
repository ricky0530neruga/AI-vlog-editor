@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\windows\setup_windows.ps1"
set "RC=%errorlevel%"
if not "%RC%"=="0" pause
exit /b %RC%

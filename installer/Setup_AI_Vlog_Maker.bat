@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "installer\setup_wizard.ps1"
set "RC=%errorlevel%"
if not "%RC%"=="0" (
 echo [ERROR] Setup wizard failed. Exit code %RC%.
 pause
)
exit /b %RC%

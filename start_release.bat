@echo off
setlocal
cd /d "%~dp0"
set "EXE=%~dp0dist\AI_Vlog_Maker\AI_Vlog_Maker.exe"
if not exist "%EXE%" (
  echo [ERROR] Packaged EXE is missing: "%EXE%"
  echo [NEXT] Run build_windows.bat to create a release first.
  pause
  exit /b 1
)
echo [INFO] Running packaged release, not the source GUI.
start "" /wait "%EXE%" %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo [ERROR] EXE returned %RC%.
  pause
)
exit /b %RC%

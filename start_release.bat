@echo off
setlocal
cd /d "%~dp0"
set "APP=%~dp0dist\AI_Vlog_Maker\AI_Vlog_Maker.exe"
if not exist "%APP%" (
    echo [ERROR] The V1.5 release EXE does not exist yet.
    echo [EXPECTED] "%APP%"
    echo [NEXT] Run build_windows.bat once, then retry start_release.bat.
    echo [INFO] start_release.bat runs only the packaged EXE; it never falls back to app.py.
    pause
    exit /b 1
)
echo [INFO] Running last packaged release: "%APP%"
echo [INFO] If it looks like the old GUI, rebuild with build_windows.bat.
start "" /wait "%APP%" %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    echo [ERROR] Packaged EXE exited with code %RC%.
    echo [HINT] Test source with start_gui.bat, then rebuild the EXE.
    pause
)
exit /b %RC%

@echo off
setlocal
cd /d "%~dp0"
if not exist "scripts\diagnose.py" (
    echo [ERROR] Missing scripts\diagnose.py.
    pause
    exit /b 1
)
if not exist "scripts\select_python.bat" (
    echo [ERROR] Missing scripts\select_python.bat.
    pause
    exit /b 1
)
call "scripts\select_python.bat" gui
if errorlevel 1 (
    echo [ERROR] No Python environment containing PySide6 found.
    echo [HINT] Run py -m pip install PySide6
    pause
    exit /b 1
)
echo [INFO] Checking Python: "%VLOG_PYTHON%" [%VLOG_PYTHON_LABEL%]
"%VLOG_PYTHON%" "scripts\diagnose.py"
set "RC=%errorlevel%"
echo [INFO] A missing PyInstaller is only relevant when building an EXE.
pause
exit /b %RC%

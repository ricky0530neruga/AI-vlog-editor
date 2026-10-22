@echo off
setlocal
cd /d "%~dp0"
if not exist "app.py" (
    echo [ERROR] app.py not found.
    pause
    exit /b 1
)
rem The Tkinter fallback can run with a Python without PySide6.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import tkinter" >nul 2>&1
    if not errorlevel 1 (
        set "LEGACY_PYTHON=.venv\Scripts\python.exe"
    )
)
if not defined LEGACY_PYTHON (
    where py >nul 2>&1
    if not errorlevel 1 set "LEGACY_PYTHON=py"
)
if not defined LEGACY_PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 set "LEGACY_PYTHON=python"
)
if not defined LEGACY_PYTHON (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)
echo [INFO] Starting v1.4 Tkinter compatibility GUI.
"%LEGACY_PYTHON%" "app.py" --legacy-gui
set "RC=%errorlevel%"
if not "%RC%"=="0" pause
exit /b %RC%

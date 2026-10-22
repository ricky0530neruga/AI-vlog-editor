@echo off
setlocal
cd /d "%~dp0"
if not exist "app.py" (
    echo [ERROR] app.py not found in "%CD%".
    pause
    exit /b 1
)
if not exist "scripts\select_python.bat" (
    echo [ERROR] Missing scripts\select_python.bat. Apply the launcher patch fully.
    pause
    exit /b 1
)
call "scripts\select_python.bat" gui
if errorlevel 1 (
    echo [ERROR] No Python environment with PySide6 was found.
    echo [HINT] If 'py app.py' works, try: py -m pip show PySide6
    echo [HINT] Otherwise: py -m pip install PySide6 python-vlc
    pause
    exit /b 1
)
echo [INFO] Starting PySide6 from Python source; not using an old EXE.
echo [INFO] Python: "%VLOG_PYTHON%" [%VLOG_PYTHON_LABEL%]
"%VLOG_PYTHON%" "app.py" %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    echo [ERROR] GUI exited with code %RC%.
    pause
)
exit /b %RC%

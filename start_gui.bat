@echo off
setlocal
cd /d "%~dp0"
if not exist "src\app.py" (
  echo [ERROR] Missing src\app.py
  pause
  exit /b 1
)
call "scripts\windows\select_python.bat" gui
if errorlevel 1 (
  echo [ERROR] A Python with PySide6 was not found.
  echo [HINT] Run setup_windows.bat or: py -m pip install -r config\requirements-windows.txt
  pause
  exit /b 1
)
echo [INFO] Starting source GUI with %VLOG_PYTHON% [%VLOG_PYTHON_LABEL%]
"%VLOG_PYTHON%" "src\app.py" %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  echo [ERROR] GUI exited with code %RC%.
  pause
)
exit /b %RC%

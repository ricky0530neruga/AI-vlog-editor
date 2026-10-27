@echo off
rem Call from a root BAT. Return VLOG_PYTHON and VLOG_PYTHON_LABEL to caller.
set "VLOG_PYTHON="
set "VLOG_PYTHON_LABEL="
if exist "%~dp0..\..\.venv\Scripts\python.exe" call :probe "%~dp0..\..\.venv\Scripts\python.exe" "project .venv"
if not defined VLOG_PYTHON (
  where py >nul 2>&1
  if not errorlevel 1 call :probe "py" "py launcher"
)
if not defined VLOG_PYTHON (
  where python >nul 2>&1
  if not errorlevel 1 call :probe "python" "PATH Python"
)
if not defined VLOG_PYTHON exit /b 1
exit /b 0
:probe
if defined VLOG_PYTHON exit /b 0
"%~1" -c "from PySide6.QtWidgets import QApplication" >nul 2>&1
if errorlevel 1 exit /b 1
set "VLOG_PYTHON=%~1"
set "VLOG_PYTHON_LABEL=%~2"
exit /b 0

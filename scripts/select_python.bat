@echo off
rem Called by another BAT. Do not use SETLOCAL: VLOG_PYTHON must be returned.
rem Usage: call "scripts\select_python.bat" gui
rem        call "scripts\select_python.bat" build
rem Prefer a working .venv; otherwise try the Python launcher and PATH Python.
set "VLOG_PYTHON="
set "VLOG_PYTHON_LABEL="

if exist "%~dp0..\.venv\Scripts\python.exe" call :probe "%~dp0..\.venv\Scripts\python.exe" "project .venv" "%~1"
if not defined VLOG_PYTHON (
    where py >nul 2>&1
    if not errorlevel 1 call :probe "py" "py launcher" "%~1"
)
if not defined VLOG_PYTHON (
    where python >nul 2>&1
    if not errorlevel 1 call :probe "python" "PATH Python" "%~1"
)
if not defined VLOG_PYTHON exit /b 1
exit /b 0

:probe
if defined VLOG_PYTHON exit /b 0
"%~1" -c "from PySide6.QtWidgets import QApplication" >nul 2>&1
if errorlevel 1 exit /b 1
if /i "%~3"=="build" (
    "%~1" -c "import PyInstaller; import vlc" >nul 2>&1
    if errorlevel 1 exit /b 1
)
set "VLOG_PYTHON=%~1"
set "VLOG_PYTHON_LABEL=%~2"
exit /b 0

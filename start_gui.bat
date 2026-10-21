@echo off
cd /d "%~dp0"
if exist "dist\AI_Vlog_Maker\AI_Vlog_Maker.exe" (
 start "" "dist\AI_Vlog_Maker\AI_Vlog_Maker.exe"
) else (
 py app.py
 if errorlevel 1 pause
)

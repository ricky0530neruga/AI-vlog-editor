@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
 echo [ERROR] Python launcher py is missing. Install Python 3.10+ and retry.
 pause
 exit /b 1
)
py -m pip install --upgrade pyinstaller
if errorlevel 1 (pause & exit /b 1)
py -m PyInstaller --noconfirm --clean --onedir --windowed --name AI_Vlog_Maker app.py
if errorlevel 1 (pause & exit /b 1)
if not exist "dist\AI_Vlog_Maker\tools" mkdir "dist\AI_Vlog_Maker\tools"
if exist "tools\ffmpeg.exe" copy /y "tools\ffmpeg.exe" "dist\AI_Vlog_Maker\tools\" >nul
if exist "tools\ffprobe.exe" copy /y "tools\ffprobe.exe" "dist\AI_Vlog_Maker\tools\" >nul
copy /y "man.txt" "dist\AI_Vlog_Maker\" >nul
if not exist "dist\AI_Vlog_Maker\AI_Vlog_Maker.exe" (echo [ERROR] EXE not found & pause & exit /b 1)
echo.
echo SUCCESS: dist\AI_Vlog_Maker\AI_Vlog_Maker.exe
echo Copy the ENTIRE dist\AI_Vlog_Maker folder, not the EXE alone.
pause

@echo off
setlocal
cd /d "%~dp0"
if not exist "src\app.py" (
  echo [ERROR] Missing src\app.py.
  pause
  exit /b 1
)
call "scripts\windows\select_python.bat" gui
if errorlevel 1 (
  echo [ERROR] Install dependencies with setup_windows.bat first.
  pause
  exit /b 1
)
"%VLOG_PYTHON%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Installing PyInstaller into the selected Python...
  "%VLOG_PYTHON%" -m pip install "PyInstaller>=6,<7"
  if errorlevel 1 (
    echo [ERROR] Could not install PyInstaller.
    pause
    exit /b 1
  )
)
"%VLOG_PYTHON%" -c "import vlc" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] python-vlc is missing in the selected Python.
  echo [HINT] Run: "%VLOG_PYTHON%" -m pip install python-vlc
  pause
  exit /b 1
)
set "FFMPEG_EXE=tools\ffmpeg.exe"
if not exist "%FFMPEG_EXE%" (
  for /f "delims=" %%G in ('where ffmpeg.exe 2^>nul') do if not exist "%FFMPEG_EXE%" set "FFMPEG_EXE=%%G"
)
set "FFPROBE_EXE=tools\ffprobe.exe"
if not exist "%FFPROBE_EXE%" (
  for /f "delims=" %%G in ('where ffprobe.exe 2^>nul') do if not exist "%FFPROBE_EXE%" set "FFPROBE_EXE=%%G"
)
if not exist "%FFMPEG_EXE%" (
  echo [ERROR] Missing ffmpeg.exe. Put it in tools or PATH.
  pause
  exit /b 1
)
if not exist "%FFPROBE_EXE%" (
  echo [ERROR] Missing ffprobe.exe. Put it in tools or PATH.
  pause
  exit /b 1
)
echo [INFO] Building src\app.py with %VLOG_PYTHON%.
"%VLOG_PYTHON%" -m PyInstaller --noconfirm --clean --onedir --windowed --name AI_Vlog_Maker --paths "%CD%\src" --distpath "%CD%\dist" --workpath "%CD%\build" --specpath "%CD%\build" --hidden-import vlc --hidden-import video_preview --hidden-import cinematic_editor --hidden-import vlog_qt --hidden-import qt_video_preview --hidden-import qt_store --hidden-import trim_times --hidden-import vlc_loader --hidden-import vlog_gui --hidden-import vlog_maker --hidden-import project_paths --hidden-import selftest "src\app.py"
if errorlevel 1 (
  echo [ERROR] PyInstaller build failed.
  pause
  exit /b 1
)
if not exist "dist\AI_Vlog_Maker\AI_Vlog_Maker.exe" (
  echo [ERROR] Built EXE was not found.
  pause
  exit /b 1
)
if not exist "dist\AI_Vlog_Maker\tools" mkdir "dist\AI_Vlog_Maker\tools"
copy /y "%FFMPEG_EXE%" "dist\AI_Vlog_Maker\tools\ffmpeg.exe" >nul
if errorlevel 1 exit /b 1
copy /y "%FFPROBE_EXE%" "dist\AI_Vlog_Maker\tools\ffprobe.exe" >nul
if errorlevel 1 exit /b 1
copy /y "man.txt" "dist\AI_Vlog_Maker\" >nul
if not exist "dist\AI_Vlog_Maker\docs" mkdir "dist\AI_Vlog_Maker\docs"
copy /y "docs\USER_GUIDE.md" "dist\AI_Vlog_Maker\docs\" >nul
if errorlevel 1 exit /b 1
echo [SUCCESS] dist\AI_Vlog_Maker\AI_Vlog_Maker.exe
echo [INFO] Building the portable five-step installer kit...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\windows\package_installer.ps1"
if errorlevel 1 (
  echo [ERROR] Installer kit packaging failed.
  pause
  exit /b 1
)
echo [NOTE] The installer can provision standalone VLC and Ollama under the selected folder.
echo [NEXT] Test start_release.bat; distribute dist\AI_Vlog_Maker_Setup.zip.
pause
exit /b 0

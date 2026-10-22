@echo off
setlocal
cd /d "%~dp0"
if not exist "app.py" (
    echo [ERROR] app.py is missing.
    pause
    exit /b 1
)
if not exist "scripts\select_python.bat" (
    echo [ERROR] Missing scripts\select_python.bat. Apply the launcher patch fully.
    pause
    exit /b 1
)
call "scripts\select_python.bat" build
if errorlevel 1 (
    echo [ERROR] No Python has PySide6, python-vlc and PyInstaller together.
    echo [HINT] In the Python where 'py app.py' works, run:
    echo        py -m pip install PyInstaller python-vlc
    echo [HINT] Or install those packages in the project .venv.
    pause
    exit /b 1
)
if not exist "tools\ffmpeg.exe" (
    echo [ERROR] Missing tools\ffmpeg.exe. Required for packaged release.
    pause
    exit /b 1
)
if not exist "tools\ffprobe.exe" (
    echo [ERROR] Missing tools\ffprobe.exe. Required for packaged release.
    pause
    exit /b 1
)
echo [INFO] Building with Python: "%VLOG_PYTHON%" [%VLOG_PYTHON_LABEL%]
"%VLOG_PYTHON%" -m PyInstaller --noconfirm --clean --onedir --windowed --name AI_Vlog_Maker --hidden-import vlc --hidden-import video_preview --hidden-import cinematic_editor --hidden-import vlog_qt --hidden-import qt_video_preview --hidden-import qt_store --hidden-import trim_times --hidden-import vlc_loader --hidden-import vlog_gui app.py
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)
if not exist "dist\AI_Vlog_Maker\AI_Vlog_Maker.exe" (
    echo [ERROR] Built EXE not found.
    pause
    exit /b 1
)
if not exist "dist\AI_Vlog_Maker\tools" mkdir "dist\AI_Vlog_Maker\tools"
copy /y "tools\ffmpeg.exe" "dist\AI_Vlog_Maker\tools\" >nul
if errorlevel 1 (
    echo [ERROR] Could not copy FFmpeg to release.
    pause
    exit /b 1
)
copy /y "tools\ffprobe.exe" "dist\AI_Vlog_Maker\tools\" >nul
if errorlevel 1 (
    echo [ERROR] Could not copy FFprobe to release.
    pause
    exit /b 1
)
if exist "man.txt" copy /y "man.txt" "dist\AI_Vlog_Maker\" >nul
if exist "docs\USER_GUIDE.md" (
    if not exist "dist\AI_Vlog_Maker\docs" mkdir "dist\AI_Vlog_Maker\docs"
    copy /y "docs\USER_GUIDE.md" "dist\AI_Vlog_Maker\docs\" >nul
)
echo [SUCCESS] dist\AI_Vlog_Maker\AI_Vlog_Maker.exe
echo [NEXT] Test start_release.bat. Copy the entire dist\AI_Vlog_Maker folder to distribute.
echo [NOTE] VLC and Ollama have separate installation requirements.
pause
exit /b 0

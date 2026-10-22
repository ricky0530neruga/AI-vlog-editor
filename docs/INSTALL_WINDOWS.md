# Windows 安裝及故障排除（v1.5 Alpha）

## 建立環境

將 ZIP 中的新檔案**合併進 v1.4 Stable 專案**，不要把 ZIP 當作獨立完整專案。建議先開新的 Git 分支。

執行 `setup_windows.bat`，在專案建立 `.venv` 並安裝 `requirements-windows.txt`。接著執行 `check_env.bat`。

- Python：使用和 PySide6 相容的 64 位元版本。Windows 上優先使用 3.12／3.13；若使用 3.15，需確認有相容的 Qt for Python wheel。
- FFmpeg：`tools/ffmpeg.exe` 和 `tools/ffprobe.exe`，或 PATH 能找到它們。打包需要 tools 下的檔案。
- VLC：安裝 VLC 64-bit；Python `python-vlc` 僅是綁定，本身不包含 LibVLC DLL。
- Ollama：需要可連線的 `127.0.0.1:11434`，並下載所需模型。設定工具不會自動拉取數 GB 模型。

## 啟動

- `start_gui.bat`：新版 Qt 原始碼，**不會自動跑舊 EXE**。
- `start_legacy.bat`：舊 Tkinter GUI 退路。
- `start_release.bat`：已打包 Windows 版；修改原始碼後必須先用 `build_windows.bat` 重新打包。

可以使用命令列診斷：

```powershell
.venv\Scripts\python.exe -c "from PySide6.QtWidgets import QApplication; print('Qt OK')"
.venv\Scripts\python.exe -c "from vlc_loader import import_vlc; print(import_vlc().libvlc_get_version())"
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

若 Qt 出現 `Could not load the Qt platform plugin windows`，優先確認使用 `.venv`、移除干擾的 `QT_PLUGIN_PATH`／`QT_QPA_PLATFORM_PLUGIN_PATH` 設定，避免混合多套 Qt 安裝。

## 注意

目前為開發版：PySide6 GUI 尚未在此交付環境進行 Windows GUI 或 EXE 實測。正式發布前應驗證影片預覽、裁切保存、排序、播放、輸出及 EXE 子行程日誌。

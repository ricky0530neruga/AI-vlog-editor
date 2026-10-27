# Windows 安裝與排錯

1. 安裝 Python 3.10–3.15、64 位元 VLC、Ollama、FFmpeg/FFprobe。
2. 執行根目錄的 `setup_windows.bat`。它會先檢查現有 Python／PySide6，已安裝則跳過下載。
3. 執行 `start_gui.bat`；或命令列 `py src/app.py`（前提是 `py` 對應環境已有套件）。
4. `py scripts/diagnose.py` 顯示 Python、PySide6、VLC、FFmpeg、Ollama 等狀態。

- **`py src/app.py` 可用，BAT 不行**：執行 `scripts/windows/select_python.bat` 需由上層 BAT `call`；檢查 `.venv` 與 `py` 是否有 PySide6。
- **缺少 `python-vlc`**：在實際執行的 Python 內執行 `-m pip install python-vlc`。
- **無法找到 FFmpeg**：將 `ffmpeg.exe` 與 `ffprobe.exe` 放入 `tools/`，或加入 Windows PATH。
- **無法開啟內建影片**：確認安裝與 Python 同位元數的 VLC；Qt 介面仍可輸入裁切時間。
- **Release 無法啟動**：需先執行 `build_windows.bat`；測試與分發時保留整個 `dist/AI_Vlog_Maker` 資料夾。
- **舊 GUI**：命令列 `py src/app.py --legacy-gui`，供問題排查。

**安裝腳本不會主動安裝系統應用程式，也不會自動下載 AI 模型。**

## v1.6 — 分發到沒有 Python／Ollama 的全新 Windows 電腦

**先在開發電腦 Build**：執行 `build_windows.bat`，接著分發 `dist/AI_Vlog_Maker_Setup.zip`。
收件者不需要 Python。解壓後雙擊 `Setup_AI_Vlog_Maker.bat`，使用五步驟精靈。

- 檢查已安裝的 VLC、Ollama、模型是否可重用。
- 選擇安裝路徑，所有由本專案主動建立的程式、模型、下載、快取及預設工作區集中在此。
- 選擇 Gemma 3 4B、12B 或兩者。下載官方 Ollama/VLC ZIP 時驗證 SHA-256。
- 最後執行 EXE 的 `--self-test`，檢查 Qt、VLC、FFmpeg/FFprobe、實際短 MP4 編碼、Ollama API 與一次短推論。

具體限制與已知風險詳見 `installer/README_INSTALLER.md`。安裝精靈不會修改全域 PATH，也不會安裝 Windows 服務或註冊解除安裝項目。若想升級，請重新執行安裝精靈；舊的模型及工作區會保留。

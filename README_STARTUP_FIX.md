# AI Vlog Maker V1.5 Alpha — Windows Launcher Fix

這是 **僅修正 Windows BAT 啟動／打包**的增量修補包，不包含 `app.py`、Qt GUI、AI 分析或 FFmpeg 核心程式。

## 原因

舊 `start_gui.bat` 強制使用 `.venv/Scripts/python.exe`，但使用者用 `pip install PySide6` 安裝在另一套 Python，因此出現 `py app.py` 正常、BAT 無法啟動的情形。

## 修改內容

- `scripts/select_python.bat`（新增）：先檢查 `.venv`，無法載入 PySide6 時自動嘗試 `py`、`python`。打包時額外檢查 PyInstaller 與 python-vlc。
- `start_gui.bat`：使用已通過 PySide6 檢查的 Python，明確啟動原始碼。
- `start_release.bat`：只啟動 `dist/AI_Vlog_Maker/AI_Vlog_Maker.exe`；找不到時顯示建立步驟。**不會自動拿 `app.py` 冒充正式版**。
- `build_windows.bat`：改用相同的 Python 偵測策略，避免又被 `.venv` 卡住。
- `check_env.bat`：診斷時也採相同 Python 偵測策略。
- `start_legacy.bat`：舊 Tkinter 退路不再強制要求 `.venv`。

## 套用

1. 在 `feature/v1.5-qt` 分支先 Commit 現況。
2. 將 ZIP 內檔案 **連同 `scripts` 子資料夾**解壓至專案根目錄，先用 Git Diff 比較後覆蓋同名 BAT。
3. 執行 `start_gui.bat`。應顯示使用的 Python 來源，並啟動 PySide6 GUI。
4. 執行 `check_env.bat` 確認必要軟體；如果 PyInstaller 顯示缺少，並不影響開啟 GUI。
5. `start_release.bat` 要能工作，必須先執行 `build_windows.bat`，且專案需有 `tools/ffmpeg.exe` 與 `tools/ffprobe.exe`。

如果 `build_windows.bat` 顯示找不到同時擁有 PySide6、python-vlc 與 PyInstaller 的 Python，可在 **`py app.py` 能執行的環境**中安裝：

```powershell
py -m pip install PyInstaller python-vlc
```

## 保證與限制

- 這次沒有更動既有影片、專案資料庫、JSON、AI 或剪輯功能。
- BAT 無法在此 Linux 執行環境原生實測；需要 Windows 實機驗證。
- 即使成功建置，VLC 原生 DLL／Qt plugins 仍需在 Windows 測試，不等於已完成 EXE 發行驗收。

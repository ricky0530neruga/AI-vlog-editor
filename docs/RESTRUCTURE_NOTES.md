# V1.5 資料夾重構與相容性

根目錄只留下五個可操作檔案：快速手冊、安裝、開發啟動、正式版啟動、打包。

| 舊位置 | 新位置 |
|---|---|
| `app.py`, `vlog_qt.py`, `vlog_maker.py` 等 | `src/` |
| `requirements-windows.txt` | `config/requirements-windows.txt` |
| `scripts/select_python.bat` | `scripts/windows/select_python.bat` |
| `scripts/setup_windows.ps1` | `scripts/windows/setup_windows.ps1` |
| `scripts/diagnose.py` | `scripts/diagnose.py` |
| `man.txt` | 根目錄 `man.txt`（精簡） |
| 原工作區／SQLite／選片 JSON | **原地保留，不搬動** |

## 核心路徑修正

- 來源模式的專案根目錄由 `src/project_paths.py` 推算；打包模式則指向 EXE 所在位置。
- UI 的 CLI 子行程執行 `src/vlog_maker.py`；FFmpeg 位置仍使用專案根目錄 `tools/`。
- PyInstaller 使用 `src/app.py`、`--paths src`，並將 FFmpeg 放入 `dist/AI_Vlog_Maker/tools/`。
- 新 BAT 不再硬性要求 `.venv`，可直接使用已安裝 PySide6 的 `py`。
- 保留原本 `AI_Vlog_Maker_V3/gui_settings.json` 使用者偏好設定路徑，避免失去既有設定。

## 遷移提醒

這個 ZIP 是可獨立解壓的完整**程式碼**版本，但**不含**第三方 FFmpeg 執行檔、VLC、Ollama、模型和個人旅遊素材。
如果你現有 Git 分支在收到這些 Patch 之後還有新修改，請在 Antigravity 逐檔比對，避免直接覆蓋。

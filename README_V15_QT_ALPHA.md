# AI Vlog Maker — v1.5 PySide6 Migration (Alpha 1)

## 這個 ZIP 是什麼？

這是**增量更新包，不是完整獨立專案**。它預期套用到 **v1.4 Stable（包含 Stability Hotfix）** 上。

### 修改／新增

- `app.py`：預設啟動 Qt，保留 `--cli` 和 `--legacy-gui`。
- `vlog_qt.py`：Qt 深色 GUI；素材／AI 分析、候選片單、拖曳排序、圖形時間軸（選取）、儲存／復原片單、執行紀錄、輸出。
- `qt_video_preview.py`：LibVLC 嵌入式裁切對話框。
- `qt_store.py`, `trim_times.py`, `vlc_loader.py`：資料、裁切與 VLC 檢查。
- Windows BAT、requirements、簡化 man.txt 和分層 docs。
- 新增 Qt 工作區相容測試及 UI smoke test。

### 沒有重寫／沒有覆蓋

- **不提供也不修改** `vlog_maker.py`、`cinematic_editor.py`、`vlog_gui.py`、`video_preview.py`；保留現有 v1.4 Stable 功能與修復。
- 原本工作區名、候選 ID、SQLite、`ui_selected_v441.json` 格式沿用。
- 音樂節拍與全片粗剪預覽仍屬後續開發項目。

## 操作（Antigravity／PowerShell）

1. 確認 `main` 已含 V1.4 Stable，沒有未提交的修改。
2. `git switch -c feature/v1.5-qt`
3. 解壓此 ZIP，將檔案合併到專案根目錄（保留原本四個後端／舊 UI 檔案）。先看 Git Diff。
4. 執行 `setup_windows.bat`、`check_env.bat`、`start_gui.bat`。
5. 從「開啟既有工作區」載入 V1.4 資料，驗證列表、裁切、排序與 FFmpeg 輸出。
6. 如需比較，執行 `start_legacy.bat`。確認正常再測試 `build_windows.bat`。

## 已做的測試

- Python 語法檢查。
- 既有 V1.4 的 FFmpeg 裁切與 Hotfix 回歸測試。
- Qt-independent 工作區、SQLite、舊版片單 JSON 與時間格式測試。
- PySide6 GUI 的 smoke test **未執行**（執行環境無 PySide6，需 Windows 端驗證）。

## 本版尚未完成

- 下方時間軸目前提供鏡頭區塊視覺化／選取；片單**拖曳排序在右側清單**、精確裁切在 VLC 視窗。還沒有時間軸邊緣拖曳裁切和全片低畫質預覽。
- 未對 Qt UI 進行 Windows 手動測試或 EXE 打包。暫時不可標記 v1.5 Stable。

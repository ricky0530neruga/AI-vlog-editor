# AI Vlog Maker — v1.5 PySide6 開發筆記

## 架構

- `app.py`：預設啟動 PySide6；`--legacy-gui` 啟動原 Tkinter；`--cli` 繼續執行原本 vlog_maker CLI。
- `vlog_qt.py`：新主視窗（左側導覽、素材清單、片單、時間軸、紀錄）。
- `qt_video_preview.py`：Qt 裁切視窗，使用 python-vlc 與系統 LibVLC。
- `qt_store.py`：與 UI 無關的工作區、SQLite 唯讀查詢、selection JSON 兼容工具。
- `trim_times.py`、`vlc_loader.py`：裁切格式與 VLC 依賴的共用工具。
- `vlog_maker.py`、`cinematic_editor.py`：保持 v1.4 內容，不在這一輪重寫 AI 與 FFmpeg。
- `vlog_gui.py`、`video_preview.py`：保留為 Tkinter 舊版退路。

## 測試

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

- `tests/test_v15_qt_store.py`：可在沒有 PySide6 的環境跑，驗證舊工作區、JSON、裁切格式。
- `tests/test_v15_qt_smoke.py`：需要 PySide6 + 可用視窗環境；檢查 Qt 主介面建立。
- 舊版 v1.4 渲染測試應繼續通過。
- GUI 的真實影片播放、libvlc Windows HWND、EXE 打包需要在 Windows 測試，不可以用通過語法測試代替。

## 工作分支

建議從 `main`（v1.4 Stable）建立 `feature/v1.5-qt`，確保更動可隨時回退。v1.5 Alpha 測試期間不要自動升版 `main`。

## 已知限制／待開發

- PySide6 時間軸第一階段僅支援選取；列拖曳排序與 In/Out 對話框已提供，但尚非專業多軌時間軸。
- v1.4 原有的節拍、輸出快取與舊 SQLite 轉換限制仍在。
- v1.4 版本路徑與 legacy JSON 名稱為相容性而保留。
- 視窗化 EXE 子行程使用 `--cli-log` 專用 UTF-8 進度紀錄檔；需要 Windows 實測確認打包後可以即時更新。

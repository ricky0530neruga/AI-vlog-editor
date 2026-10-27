# 開發與版本管理

## 專案結構

- `src/`：Python 主程式、PySide6／Tkinter UI、AI 分析與 FFmpeg 核心。
- `config/`：pip 套件需求（不是使用者剪輯資料）。
- `scripts/windows/`：安裝與 Python 環境自動偵測腳本。
- `scripts/`：診斷與測試執行器。
- `tests/`：單元、回歸與可選的 Qt Smoke Test。
- `tools/`：放置 FFmpeg 與 FFprobe（可改用 PATH）。
- `docs/`：說明書和歷史文件。

## 常用指令

```powershell
py src/app.py
py src/app.py --legacy-gui
py src/app.py --cli --help
py scripts/run_tests.py
py scripts/diagnose.py
```

## 安全原則

- 此版本**由既有 V1.4 Stable + V1.5 Alpha + Launcher Fix 更新包整合**，不是直接下載 GitHub 最新 main。
- 請先在 `feature/v1.5-qt-structure` 測試，並用 Git Diff 核對自己新增的程式。
- 不搬移原有旅行素材、使用者工作區、SQLite 或 `ui_selected_v441.json`；它們的目錄由使用者選擇。
- `dist/`、`build/`、`.venv/` 為執行或打包生成，不包含在原始碼交付包。
- Windows BAT、LibVLC 及 PyInstaller 尚需 Windows 實機驗證；不可直接標 Stable。

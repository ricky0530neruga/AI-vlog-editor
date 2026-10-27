# AI Vlog Maker V1.6 — Windows 五步驟安裝精靈

此版本是安裝精靈 **Alpha**，整合 V1.5 PySide6 介面與既有 AI／FFmpeg 後端，不修改舊版工作區的資料格式。

## 建置電腦（需 Python、PySide6、PyInstaller）

在專案根目錄執行 `build_windows.bat`。它會：

1. 編譯 `src/app.py` 為 Windows onedir EXE。
2. 從 `tools/` 或 PATH 將 `ffmpeg.exe` 與 `ffprobe.exe` 放入 EXE 旁的 `tools/`。
3. 建立 `dist/AI_Vlog_Maker_Setup/`，內含五步驟安裝精靈和 `payload/App/`。
4. 建立 `dist/AI_Vlog_Maker_Setup.zip` 供其他 Windows 電腦使用。

**注意**：這份原始碼 ZIP 不含 Windows EXE，必須在 Windows 執行 Build 後再散布。不要直接把原始碼 ZIP 當成可用的離線安裝包。

## 乾淨 Windows 電腦（不需 Python）

將 `AI_Vlog_Maker_Setup.zip` 解壓，雙擊 `Setup_AI_Vlog_Maker.bat`。

安裝精靈會依序：

1. **檢查**正式版 EXE、FFmpeg、VLC、Ollama、模型是否存在。
2. **顯示**已存在／需下載的項目。
3. **選擇安裝路徑**，檢查路徑是否可寫入。
4. **勾選模型** Gemma 3 4B／12B；有則重用。
5. **執行安裝與自我測試**：PySide6、FFmpeg、FFprobe、VLC、Ollama API 與指定模型。

安裝完成後雙擊 `<安裝目錄>/Start_AI_Vlog_Maker.bat`。

## 集中儲存

```text
<選定安裝路徑>/
  Start_AI_Vlog_Maker.bat
  App/                 打包好的 exe、PySide6、FFmpeg
  Runtime/Ollama/      官方 Ollama 獨立 CLI（若需要）
  Runtime/VLC/         官方 VLC ZIP（若需要）
  Runtime/Models/      私有 Ollama 模型
  Data/                GUI 設定、安裝紀錄、Ollama home
  Workspaces/          預設影片專案
  Cache/               已下載安裝資源（可清除）
  Temp/                應用程式暫存
  Logs/                日誌和自檢結果
```

預設不新增系統 PATH、登錄機碼、Windows 服務或桌面捷徑。重用已經安裝在別處的 VLC / Ollama 時，只讀取原有程式；不搬動原有檔案。如果系統 Ollama **具備全部勾選的模型**，重用既有模型；否則啟動獨立 11435 服務，將其模型資料保存在選定安裝路徑。當兩處模型庫不同時，可能需要另外下載同一個模型，精靈不會修改使用者原本的 Ollama 模型目錄。

**重要限制**：Windows、VLC 或 Ollama 自身仍可能產生系統暫存、驅動程式快取及作業系統記錄，無法承諾「任何程序絕不在安裝目錄外寫入任何檔案」。此版本保證的是我們**主動建立的程式檔、模型、下載、專案與日誌**集中管理，不修改使用者全域環境變數。

## 依賴來源與驗證

- Ollama CLI (Windows x64)：官方 GitHub Release `v0.40.7`，下載後比對固定 SHA-256。
- VLC ZIP (Windows x64)：官方 VideoLAN `v3.0.24`，下載後比對固定 SHA-256。
- AI 模型：透過使用者本機或獨立 Ollama API pull，核對 `/api/tags`。
- PySide6、python-vlc 和 FFmpeg：已在 Build 電腦準備，隨 EXE/`tools/` 散布。

如下載或解壓縮失敗，保留正確的下載快取，重新執行可繼續；雜湊不匹配的檔案會被刪除並報錯。

## 驗收限制

自檢只驗證組件可載入、FFmpeg 可呼叫、Ollama API 可連線且模型存在。**無法單靠自檢驗證實際 GPU 加速、滑動時間軸、完整影片播放、長片輸出品質或跨電腦相容性。** 請在乾淨 Windows 10／11 x64 實機進行首次安裝和最終影片輸出測試。

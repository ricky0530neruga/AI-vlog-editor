# V1.6 架構審查（2026-10-28）

審查基線：實際工作區 `featrue/v1.5`，`d757f884531a4568bc12e6a94741cb571f8aae1d`。
未提交的 build/ 為原有產物，不納入改動。不是以 GitHub 預設分支作推定。

## 資料流與依賴

`vlog_maker.scan` → FFprobe → SQLite media；來源 size/mtime 變化時刪除該來源候選及縮圖快取。
`candidates` 按 duration/step 均分時間、受 max_per_video 上限約束；不是直接每 step 秒抽樣。
`analyze` → FFmpeg 縮圖/dHash/亮度 → Ollama 快篩與少量複審 → candidates。
`choose` 以分數、event、角色、時間、來源/分類多樣性與 dHash 產生 plan。
`choose_selected` 接收人工 ID/順序/裁切；`render` → cinematic_editor 分組編碼、交叉淡化、音訊混合。
cinematic_editor 反向 import core，形成雙向依賴；暫保留穩定渲染介面。

## GUI 與阻塞

Qt 掃描/渲染經背景 thread 啟動 CLI subprocess，訊息佇列回主執行緒，應保留。
候選查詢、prune、推薦和片單重建仍在 GUI thread；大量片單及網路磁碟可能卡頓。
Tkinter/Qt 各自維護選片及工作區操作；qt_store 已抽出分頁、唯讀 DB 與 JSON 原子寫入。
qt_video_preview 是 LibVLC 顯示與裁切 adapter；不應承擔分析。recommend 原本直接清空 manual_trims 並寫入片單。

## 儲存一致性

SQLite 是媒體與分析快取；JSON 是人工選片/排除/裁切。沒有跨檔交易或外鍵。
prune_selection 驗證 ID/檔案及裁切，但來源改變、搬移或重新掃描仍可能令人工 ID 失效。
既有 connect 是逐欄 additive upgrade；不能把舊 score 解讀成新多維分數。
快取鍵依賴 path/position，失效依賴 size/mtime；缺內容指紋、Prompt 版本、schema 版本。
JSON 原子 replace 可減少半寫入，固定 .tmp 名稱仍有多寫者競態。

## 評分與重複偵測限制

vision 對缺失/錯型數字回填 50 並 clamp，可能將無效回答當作有效分析。
溫度 0.1 不能保證可重現；role 與單影格推定敘事關係混合。
CPU 預篩由單張亮度 <13 或同來源 dHash 判斷跳過，無法保留片段內其他有效畫面。
dHash 對純色誤判且受視角/光線影響，不能代表同景點語意重複。
現有 choose 已有多樣性與近似去重，不應描述為只按單一 score 排序。

## 保留與抽取

保留 CLI/兩套 GUI、人工裁切、SQLite 欄位、FFmpeg/VLC adapters、分組 renderer。
增量抽取：候選區間/影格策略、技術訊號、多維 schema/驗證、獨立版本快取、推薦及 benchmark。
新策略採 opt-in；在固定素材比較前不改現有預設。

## 測試證據

原有 26 tests：23 passed，3 skipped（Tk display、FFmpeg、PySide6）。
現有測試覆蓋裁切鎖定、來源更新清除縮圖、JSON/prune、CLI、安裝器文字契約。
未覆蓋真實 Ollama、完整 scan/analyze/render、場景切分、多維驗證、近似重複品質、Qt 實際互動。
自動測試成功不代表成片品質改善。

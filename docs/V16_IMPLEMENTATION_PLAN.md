# V1.6 增量實作計畫

每階段獨立本機 commit，執行 `scripts/run_tests.py`；不 push/merge/release。

0. 審查實際工作區、建立現況與技術債文件。
1. benchmark：固定來源完整雜湊、人工標註模板、舊快取唯讀重播/隔離掃描分析、JSON/Markdown、版本比較。
2. 固定時間/FFmpeg scene 兩種 opt-in 候選策略，精確區間、多代表影格、技術品質與保守去重；保留現有預設。
3. 嚴格多維 schema、模型/Prompt 版本、可續跑獨立 sidecar；舊 SQLite 無需遷移。
4. 多維推薦預覽、來源/分類/近似去重、目標時長、理由；人工片單與鎖定裁切保持。
5. 回歸、自動測試/實際素材/未驗證矩陣、changelog、V1.7 建議。

重大破壞性格式變更、清除資料先取得批准；新增獨立 sidecar 不修改舊格式。
scene 偵測優先沿用 FFmpeg，不先安裝 PySceneDetect。需評估轉場、短鏡頭、平移誤報及低成本降採樣漏切。
Benchmark 使用固定 LLM 回答或既有 cache 重播才能比較決定性；現場 LLM 耗時與失敗獨立記錄。
人工 relevance、precision/recall 未標註時為「尚未評估」，不產生虛構綜合品質分數。

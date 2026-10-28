# 技術債

|優先級|問題|增量處理方向|
|---|---|---|
|P0|推薦清空人工裁切|既有片單保護、獨立推薦預覽|
|P0|LLM 無效欄位回填分數|新版本 strict schema，失敗保留 error|
|P1|單影格預篩漏掉好片段|多影格訊號，保留不確定候選|
|P1|沒有固定素材品質基準|唯讀 manifest、人工標註、版本結果比較|
|P1|舊模型/Prompt 快取語意不完整|獨立版本快取，不轉換或清空舊表|
|P1|size/mtime 失效可能漏掉內容變化|benchmark 使用 SHA256；正式掃描另行評估成本|
|P2|核心與 renderer 雙向依賴|日後抽取 subprocess/media adapter|
|P2|GUI thread 上同步讀庫與推薦|量測後移到 worker；保留 GUI 範圍|
|P2|SQLite/JSON 無跨檔交易|保留驗證/prune，將來工作區 revision 與衝突偵測|
|P2|dHash 無法辨識景點|先保守多影格匹配；V1.7 評估 CPU embedding 成本|
|P2|測試依賴缺少而 skip|報告分開列出 passed/skipped/實際素材未驗證|

不在本次處理：Tk→Qt 全面遷移、renderer 重寫、敘事引擎、全依賴升級。

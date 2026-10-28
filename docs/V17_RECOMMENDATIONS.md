# V1.7 敘事規劃引擎建議

先凍結並人工標註固定素材，採 clip inclusion、事件覆蓋、冗餘與整體觀看體驗分開評估，不設虛構綜合分數。
維持 V1.6 observations（technical/interest/event/category/description）與整體 story relevance 分離。

規劃器以完整候選集合、旅行時間證據、使用者主題/時長和鎖定片段作輸入，產生可撤銷 proposal。
用集合層的事件覆蓋與多樣性作約束；以來源時間/事件圖處理旅程順序，缺 EXIF 時不把 mtime 當真實旅程時間。
冗餘先用多影格視覺比對，之後評估小型 CPU embedding 與可校正閾值，另建版本化 index。

先提供純函式 planner、明確序列 schema、理由與約束違反報告，再將 GUI preview/apply/undo 串接。
人工鎖定片段的時間與順序必須具優先權；不足素材明示，不以幻覺補足故事。
規劃器與 render adapter 共享已驗證區間，處理轉場 overlap 但不越過場景或人工 trim。
量測各階段耗時後再決定 worker 數、取消策略、磁碟快取與可選 GPU，不先重寫 renderer。
AI 部分以固定輸出、schema 壞輸出、離線/超時、模型變更、斷點續跑作回歸案例。
跨檔案工作區 revision/人工選片同步可另開非破壞性遷移設計，需先審核相容方案。

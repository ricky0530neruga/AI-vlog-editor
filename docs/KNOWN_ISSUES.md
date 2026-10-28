# 已知問題與限制

- 新多維引擎先提供獨立 CLI；Qt 預設仍使用既有單一 score cache，尚未在 GUI 顯示多維欄位或匯入新 candidate IDs。
- 舊版 vision 的寬鬆回填行為保留在 legacy baseline；嚴格驗證僅適用新引擎，不可混淆兩者。
- 舊 CPU 預篩單張跳過仍是 legacy 分析行為；新候選路徑不沿用該淘汰規則。
- 無人工標註與盲測，尚無成片品質提升證據。固定/scene 的樣本單位不同，不可直接用候選總數推斷 precision。
- dHash 是視覺 proxy，並非景點語意辨識；遠近視角及光線不同可能漏重，紋理相似可能誤重。
- 技術品質是低解析 proxy。camera_shake=null；motion_proxy 是畫面變化，未完成真正運動估計/相機軌跡分析。
- 長場景最多三張代表影格可能漏短暫事件；場景邊界不保證內容最佳剪點。
- 新推薦不作完整敘事規劃，也不自動填補素材不足。預設 LLM budget 12，不會對所有影格推理。
- 新 proposal 輸出採硬切以維持區間，舊 GUI cinematic 淡化/音訊/節奏功能保留原路徑。
- 固定 seed/temperature 不保證跨模型、Ollama 版本或硬體完全一致；比較應重用有效快取。
- CPU 三影格推理明顯耗時；每次 API timeout 120 秒，失敗會留 raw/error 並允許重試。
- GUI/VLC 的長時間使用、完整 180 秒真實旅遊成片與人工觀看評分尚未完成；煙霧測試不能取代這些驗收。

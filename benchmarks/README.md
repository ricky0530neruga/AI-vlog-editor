# 可重現基準

所有來源唯讀。私人 manifest、標註、cache、結果放 `benchmarks/local/`（Git 忽略），不要將影片複製進專案。
輸出必須是新目錄，且不能位於來源素材目錄。完整 SHA256 會讀取所有來源；執行前後再次驗證。

```powershell
python src/benchmark_v16.py manifest --input "C:\media\Travel1" --out benchmarks/local/travel1
python src/benchmark_v16.py run --manifest benchmarks/local/travel1/manifest.json --out benchmarks/local/legacy
# 有 Ollama 與模型時，明確選擇執行 AI（可能耗時）：
python src/benchmark_v16.py run --manifest benchmarks/local/travel1/manifest.json --out benchmarks/local/live --analyze --model gemma3:4b
# 重播既有分析，不修改原 SQLite，不呼叫模型：
python src/benchmark_v16.py run --manifest benchmarks/local/travel1/manifest.json --index "C:\workspace\index.sqlite" --out benchmarks/local/replay
python src/benchmark_v16.py compare benchmarks/local/legacy/result.json benchmarks/local/live/result.json --out benchmarks/local/comparison.json
```

annotations.json 儲存人工 include/exclude 時間段與備註，與 manifest_id 綁定。沒有人工標註時品質為「尚未評估」。
目前工具不從主觀標註推導品質分數；人工可對照 plan 閱看。dHash 重複率只是 proxy；缺 hash 時為 null。
live 模式保留模型名、revision、錯誤及耗時；Ollama 不是決定性來源。重播相同快取用於決定性回歸。
候選模式不執行 AI，所以未評分片段不會被推薦；不可把空 plan 解讀成品質下降。

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

## V1.6 opt-in 引擎

```powershell
python src/benchmark_v16.py candidates --manifest benchmarks/local/travel1/manifest.json --out benchmarks/local/fixed-v16 --strategy fixed
python src/benchmark_v16.py candidates --manifest benchmarks/local/travel1/manifest.json --out benchmarks/local/scene-v16 --strategy scene
# 預設最多輪選 12 個候選、每候選最多三張代表影格；0 表示全部（CPU 可能很久）
python src/benchmark_v16.py assess --manifest benchmarks/local/travel1/manifest.json --candidates benchmarks/local/fixed-v16/result.json --out benchmarks/local/ai --limit 6
# 續跑：新報告目錄，重用先前 sidecar，成功項目不再推理，失敗項目重試
python src/benchmark_v16.py assess --manifest benchmarks/local/travel1/manifest.json --candidates benchmarks/local/fixed-v16/result.json --cache benchmarks/local/ai/assessments.sqlite --out benchmarks/local/ai-resume --limit 6
python src/benchmark_v16.py recommend --assessments benchmarks/local/ai/result.json --out benchmarks/local/proposal.json --seconds 180
python src/benchmark_v16.py render-proposal --manifest benchmarks/local/travel1/manifest.json --plan benchmarks/local/proposal.json --out benchmarks/local/render
python src/benchmark_v16.py annotations --manifest benchmarks/local/travel1/manifest.json --file benchmarks/local/travel1/annotations.json --out benchmarks/local/validated-annotations.json
```

`recommend --existing-plan previous-proposal.json` 保留已有 plan（包含鎖定裁切），只填剩餘時長。
`--review-file` 可接受 excluded_ids / excluded_paths。輸出檔必須不存在，避免覆蓋人工片單。
新候選 ID 與舊 SQLite ID 不相同；V1.6 多維引擎先以此 CLI 提供，不把多維分數寫回舊 score。
Qt 繼續使用既有分析；有人工片單時「AI 建議預覽」另存 JSON，使用者可手動加入建議。
render-proposal 沿用 cinematic_editor，硬切且鎖定場景區間，避免跨淡化延伸超出偵測場景。
不足 180 秒時明列 shortfall，不重複或慢放素材。

CPU 模式 options 使用 temperature=0、seed=0、num_gpu=0，記錄模型 digest、Prompt/schema。
仍不宣稱跨硬體/版本位元一致；確定性測試使用固定回答及有效快取重播。
API 參考：[Ollama 官方 API](https://github.com/ollama/ollama/blob/main/docs/api.md)。

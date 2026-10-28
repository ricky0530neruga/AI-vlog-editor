# 候選策略評估

沿用 FFmpeg `select` 的 scene 與 `showinfo` timestamps，縮小至寬 160 後計算影格差異，仍解碼原生時間序列。
依據：[FFmpeg 官方 filter 文件](https://www.ffmpeg.org/ffmpeg-filters.html#select_002c-aselect)。
不新增 PySceneDetect 套件；其專用 detector/統計日後可作對照，但目前已有 FFmpeg，先避免部署額外依賴。

固定模式遵循原本 min(maximum, ceil(duration/step)) 均分；新模式保留 [start,end]。
scene 模式保留每個偵測場景邊界，不使用候選上限截斷場景；超過 4 秒場景抽 20/50/80% 三張。
這三張並非足以保證整段品質；技術訊號不直接淘汰候選。
代表影格亮度、低解析 Laplacian variance 為品質 proxy；相鄰 0.1 秒像素差是運動風險，不能可靠辨別相機晃動，camera_shake=null。
多影格 dHash 需雙向至少 2/3 匹配且排除低對比圖，仍不能證明是同景點。

限制：淡入淡出/平移可能誤報；壓縮與縮小可能漏掉細微切換；短場景單影格不強制去重。
長場景只有限代表影格，不保證找到短暫事件；V1.7 可加入可控的時間覆蓋率。
scene 不作預設；固定素材比較報告置於本機 benchmark 及驗收文件，品質必須人工評估。

```powershell
python src/benchmark_v16.py candidates --manifest benchmarks/local/travel1/manifest.json --out benchmarks/local/fixed --strategy fixed
python src/benchmark_v16.py candidates --manifest benchmarks/local/travel1/manifest.json --out benchmarks/local/scene --strategy scene
```

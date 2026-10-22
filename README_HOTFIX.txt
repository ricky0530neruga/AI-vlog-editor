AI Vlog Maker V1.4 — Stability Hotfix（增量修正）

請先備份並 Commit 現有專案，建議在 feature/v1.4-preview-trim 分支測試。
請將 ZIP 中的檔案複製到同一個 AI Vlog Maker 專案根目錄，覆蓋 4 個舊檔案，並新增 tests/test_hotfix_v141.py 與更新紀錄。
本 ZIP 不是可獨立執行的整套軟體，不含舊版 app.py 等未變更檔案。

用 Antigravity Diff 仔細比對，特別是 vlog_gui.py（可能有你自行修改的中文介面文字）。
從專案目錄執行：
  py -m unittest discover -s tests -v
  py app.py
在左側候選列表、右側已選片單輪流點選並開啟預覽；測試關閉／再次播放／保存裁切，最後輸出一段短片。

通過後在原本分支 Commit：
  git status
  git add vlog_gui.py video_preview.py vlog_maker.py man.txt tests/test_hotfix_v141.py CHANGELOG_V1_4_HOTFIX.txt README_HOTFIX.txt
  git commit -m "fix: stabilize v1.4 preview and selection"
  git push

重要：已編譯的 dist EXE 不會因為 Python 原始碼更新而自動更新；需要重打包。
本包以先前 V1.4 Preview & Trim PATCH 為基準，未取得你在本機或 GitHub 後續修改的最新程式，請勿未比對就強制覆蓋。

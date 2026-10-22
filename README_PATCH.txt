AI Vlog Maker v1.4 — Preview & Trim PATCH（從 v1.3 穩定版升級）

先執行 git status，確認工作區已提交，從 main 建立 feature/v1.4-preview-trim 分支。
本 ZIP 只有修改／新增的檔案，不包含完整專案。
請將檔案覆蓋／加入原本專案根目錄；已有個人化修改的檔案請先用 Antigravity Diff 比對。

啟動測試：在專案根目錄輸入「py -m pip install python-vlc」及「py app.py」。
同時要安裝 64 位元 VLC Media Player（python-vlc 只是綁定，不包含播放核心）。
不要直接使用舊 start_gui.bat 啟動預先打包的 dist EXE；請先重打包。

測試：py -m unittest discover -s tests -p test_v14_trim.py -v
GUI 可再使用 tests/test_gui_smoke.py 於有圖形介面的系統測試。
原始媒體檔案唯讀；沿用原本的選片與分析快取。

本增量包基於先前交付的 V4.4.2 Candidate Fix + GUI Hotfix（你重新命名為 v1.3 的基礎），
未取得你 GitHub 目前 main 上自行調整的 GUI 文字；必須先 Diff，不建議直接在 main 覆蓋。

"""後端骨架 — 讓多個真人能同時連進來,在同一個案件上協作。

引擎(trustagent/)一行不動,只是:
  1. 把稽核鏈與授權存進 SQLite(跨 request、跨重啟不消失)
  2. 加一層最小認證(誰登入,Principal 就是誰)
  3. 把 run.py 在程式碼裡做的事,變成 HTTP 端點

對照說明見 backend/README.md。
"""

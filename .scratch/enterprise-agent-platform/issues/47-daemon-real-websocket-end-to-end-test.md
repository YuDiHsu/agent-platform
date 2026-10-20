# 47: 本機 Daemon 真實 WebSocket 端到端測試（審查後續：10）

**What to build:** 目前 Daemon 的路由、撤銷與跨 Worker 轉送都只用假 Socket 測過；真實的 `daemon.py` 只手動驗證過「能連上並記錄上次連線」。補一個自動化端到端測試：啟動真實 API（uvicorn）與 `packages/local-mcp-daemon/daemon.py`，用配對權杖連線，經工具匯流排讀寫 Daemon 資料夾內的檔案，執行一個允許的 CLI 指令，最後撤銷配對並確認 Daemon 收到 1008 後停止重連。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 測試以真實 WebSocket 連線完成配對、讀取、寫入與 CLI 執行
- [ ] 錯誤或已撤銷的權杖連線被拒（1008），Daemon 結束而非無限重試
- [ ] 撤銷配對後，已連線的 Daemon 被中斷，後續呼叫回傳 Daemon 未連線
- [ ] 測試結束時關閉所有子行程，不會讓 pytest 卡住
- [ ] 完整測試套件全綠

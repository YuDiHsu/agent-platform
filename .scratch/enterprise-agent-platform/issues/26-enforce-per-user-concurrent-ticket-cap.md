# 26: 每位使用者併發工單配額確實生效（審查後續：02）

**What to build:** 使用者同時開兩個以上對話時，所有 Session 合計處於 `IN_PROGRESS` 的工單數絕不超過 `max_concurrent_tickets`。超過配額的工單維持排隊，當有名額釋出時在**同一個 DAG** 內接續執行，而不是讓下一則訊息另開新 DAG。目前計數只算其他 Session，且 advisory lock 在認領前就釋放，兩個 Session 可同時通過檢查。

**Blocked by:** 25: DAG 快照型別化與工作區還原整併

**Status:** ready-for-agent

- [ ] 配額計數涵蓋該使用者所有 Session（含目前 Session）的 `IN_PROGRESS` 工單
- [ ] 檢查與認領在同一個鎖／交易內完成，並行請求無法同時越過上限
- [ ] 超過配額時工單保持排隊，名額釋出後於原 DAG 接續；使用者在對話中看到「等待併發名額」的繁中狀態
- [ ] 測試：兩個 Session 併發送出，`IN_PROGRESS` 數從未超過上限，且全部工單最終完成
- [ ] 完整測試套件全綠

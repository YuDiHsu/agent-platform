# 25: DAG 快照型別化與工作區還原整併（審查後續：02）

**What to build:** Supervisor 在休眠、斷路與同步時寫入 checkpoint 的 DAG 快照，改用既有的 `DAGTaskNode` 型別，且「以工單最新狀態合併快照」只有一份實作。Bootstrap 與組織圖共用同一個上級角色（`reports_to_code`）解析；前端狀態機處理 SSE 時共用一個附加訊息的輔助；聊天頁在掛載與登入後共用同一段「bootstrap → 載入 Session」流程。使用者看到的 DAG、對話還原與組織圖完全不變。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] DAG 快照以 `DAGTaskNode`（或其序列化型別）傳遞，不再是 `list[dict[str, Any]]`
- [ ] 休眠、斷路、同步三處共用同一個「以工單狀態合併快照」函式
- [ ] `reports_to_code` 解析只定義一次，bootstrap 與組織圖 API 共用
- [ ] 前端 SSE 事件處理共用附加訊息輔助；聊天頁掛載與登入共用同一段還原流程
- [ ] Supervisor 的併發 Semaphore 與「認領 → 跳數檢查 → 執行」輔助改為意圖清楚的名稱
- [ ] 既有 DAG／還原測試不改斷言即全綠；tsc 乾淨

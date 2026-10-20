# 39: CLI 準備流程與執行結果型別整併（審查後續：09）

**What to build:** 每次 CLI 呼叫只做一次「驗證參數 → 渲染指令 → 判定等級」並只寫一次稽核，角色執行器與 CLI adapter 共用這份準備結果。執行結果成為型別化的值，在執行、`cli_output` 事件與 `cli_execution_logs` 之間傳遞。`execute_skill_cli` 的參數 Schema 只有一個來源；「是不是 CLI 工具」的判斷集中一處；前端兩個元件共用審批後處理 `cli_output` 的邏輯。使用者看到的 CLI 行為不變。

**Blocked by:** 38: COMMIT 等級 CLI 技能於執行器層強制審批

**Status:** ready-for-agent

- [ ] 單次呼叫只準備一次，資料庫查詢與稽核不重複
- [ ] 執行結果以型別化物件傳遞，移除腳本中的 `type: ignore`
- [ ] `execute_skill_cli` Schema 單一來源（adapter 與種子不再各寫一份）
- [ ] CLI 工具判斷集中，角色執行器、審批 API、匯流排不再各自比對工具名
- [ ] 瀏覽器讀檔與 Daemon 執行的 RPC 結果解析共用；前端 `cli_output` 後處理共用
- [ ] 意圖不清的名稱（拒絕重生輔助、`first`、`cli_event`、選項黏合函式、`round(...) + 0.0`）改名或說明
- [ ] 09 的測試不改斷言即全綠；mypy、tsc 乾淨

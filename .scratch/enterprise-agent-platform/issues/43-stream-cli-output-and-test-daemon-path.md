# 43: CLI 輸出即時串流與本機 Daemon 路徑測試（審查後續：09）

**What to build:** 使用者執行 CLI 技能時，終端機卡片隨著指令輸出逐段更新，而不是等命令結束才一次出現；從審批卡核准後的執行也走同一條 SSE 串流，而非靠 API 的 JSON 回應。`LOCAL_DAEMON_CLI` 執行路徑有端到端測試。

**Blocked by:** 39: CLI 準備流程與執行結果型別整併

**Status:** ready-for-agent

- [ ] 沙盒執行過程中以 SSE 逐段送出 `cli_output`（stdout／stderr 分開、保留 ANSI）
- [ ] 審批核准後的 CLI 執行同樣經 SSE 串流到對話
- [ ] 重新登入仍能還原完整終端紀錄
- [ ] 新增 `LOCAL_DAEMON_CLI` 路徑測試（假 Daemon）
- [ ] 瀏覽器驗證終端機卡片逐段更新

## Comments

- 10 完成後：`LOCAL_DAEMON_CLI` 會送到使用者最近連線的配對 Daemon（`daemon_handle`），路由欄位為 `daemon:<user>:<pairing>`。假 Daemon 測試需先建立配對，並以 `ws_rpc_manager.register_daemon(user_id, pairing_id, socket)` 註冊；沒有配對時回傳「本機 Local MCP Daemon 未連線」。

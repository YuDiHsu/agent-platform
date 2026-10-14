# 10: 24/7 背景排程常駐工作（Celery Heartbeats）、原子鎖定工單 Worker 與選配本機 Daemon

**What to build:** 建立 24/7 全天候非同步工單執行器與定時常駐排程（Celery Beat + Redis），並提供給進階工程師選配的輕量級本機守護進程（Local MCP Daemon）。背景 Worker 使用 PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` 實現 Paperclip 風格的原子工單鎖定，避免多 Worker 重複執行同一張工單；支援每日定時自動觸發例行任務（如每日 08:30 自動分類未讀信件與發送 Teams 晨間摘要）。當使用者關閉瀏覽器分頁時，伺服器端 MCP 工具仍可於背景正常運作；若背景工單需要讀取未連線的瀏覽器本機掛載，系統會優雅降級並通知使用者，或當使用者終端已啟動選配的 `Local MCP Daemon` 時，無縫由 Daemon 接手本機檔案讀寫（`CLIENT_FS_READ` / `CLIENT_FS_WRITE`）與本機 CLI/Git 診斷指令（`DAEMON_EXEC_CLI`，如 `SKILL_SE_PYTEST_AND_GIT_DIAGNOSTICS`）。

**Blocked by:** 06: 可插拔 BaseToolAdapter 擴充接口、四大企業 MCP 連接器與高併發低延遲工具匯流排, 07: 跨 Worker Redis Pub/Sub 瀏覽器本機反向 RPC 橋接、記憶體文件解析與紅綠 Diff 寫入, 09: 雙目標參數化防注入 CLI 執行器、併發限流 Rootless Docker 沙盒與即時 ANSI 終端機卡片

**Status:** ready-for-agent

- [ ] 背景工單 Worker 採用 `SELECT ... FOR UPDATE SKIP LOCKED` 原子爭取 `PENDING` 工單並記錄 `locked_by_worker` 與 `locked_at`，防止併發競爭（`REQ-002`, `REQ-011`）
- [ ] 定時排程器（Heartbeat Cron）支援設定週期性背景工單，在使用者瀏覽器關閉狀態下仍可透過個人 OBO 權杖執行伺服器端連接器任務（`REQ-011`, `TC-M4-01`）
- [ ] 當背景任務嘗試存取離線的 `BROWSER_FS_API` 本機掛載時，不會導致 Worker 崩潰，而是優雅記錄狀態並透過通知管道提醒使用者開啟頁面授權（`TC-M4-01`）
- [ ] 選配的輕量 `Local MCP Daemon` 可透過 WebSocket 隧道註冊連線，在瀏覽器關閉時無縫處理被授權目錄內的檔案讀寫與 `LOCAL_DAEMON_CLI` 指令執行（含路徑邊界與黑名單檢查）（`REQ-005`, `REQ-016`, `TC-M4-02`）

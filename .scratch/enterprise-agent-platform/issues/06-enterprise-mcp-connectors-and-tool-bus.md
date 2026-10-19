# 06: 可插拔 BaseToolAdapter 擴充接口、四大企業 MCP 連接器與高併發低延遲工具匯流排

**What to build:** 在統一工具執行匯流排（`UnifiedToolBus`）定義標準可插拔 `BaseToolAdapter` 雙軌接口，讓後端工程師既能以 Python `@register_tool_adapter` 裝飾器接入新工具模組，也能不改程式碼、直接透過資料庫與管理 API 動態掛載遠端標準 MCP Server 或 HTTP Webhook。在該接口上實作四大企業內部 MCP 連接器（Microsoft Office 365、Microsoft Teams、Slack 與通用 IMAP/SMTP 信箱），並導入四大高併發低延遲機制：同回合多筆工具呼叫透過 `asyncio.gather()` 平行執行、單一 Adapter 獨立 Timeout（預設 10 秒）與連續失敗斷路器（Circuit Breaker）、冪等 `READ` 工具 Redis 短效快取（TTL 60 秒），以及全域共用 `httpx.AsyncClient` 長連線池與外部 I/O 期間釋放資料庫連線。

**Blocked by:** 04: 個人 OBO 權杖加密金庫、可插拔 tools_registry 三層偏好開關與動態 Tool RAG, 05: HITL 人工審批安全閘門（READ / DRAFT / COMMIT）與狀態機斷點續傳

**Status:** ready-for-agent

- [x] 定義 `BaseToolAdapter` 抽象介面（含 `namespace`、`list_tools()`、`health_check()`、`execute()`），支援 `@register_tool_adapter` 程式碼自動註冊同步至 `tools_registry`，以及 `RemoteMCPToolAdapter` / `HttpWebhookToolAdapter` 動態遠端掛載（`ADR-0002`）
- [x] 實作 Microsoft 365 MCP（信件搜尋 `READ`、建立草稿 `DRAFT`、寄出信件 `COMMIT`、尋找會議空檔 `READ`、建立行事曆會議 `COMMIT`、讀取 OneDrive 檔案 `READ`）、Microsoft Teams MCP（頻道討論讀取、發送訊息與 HITL Adaptive Approval Cards）、Slack MCP 與通用 IMAP/SMTP 信箱連接器（`REQ-006`, `TC-M2-01`）
- [x] `UnifiedToolBus` 強制雙重驗證「角色授權 $\cap$ 使用者個人啟用」權限；若代理嘗試呼叫使用者已關閉或未授權給該角色的工具，立即拒絕執行（`ADR-0002`）
- [x] 實作低延遲與防慢機制：當代理單次輸出多筆 `READ`/`DRAFT` 工具呼叫時，透過 `asyncio.gather()` 平行併發派發（總耗時趨近單一最慢工具而非累加）；為每個 Adapter 實作獨立 Timeout（預設 `10s`）與斷路器，並為同一 Session 內相同參數的冪等 `READ` 呼叫提供 Redis 短效快取（`ADR-0002`）
- [x] 高併發連線保護：所有外部連接器共用 Lifespan 級別的 `httpx.AsyncClient` 連線池，且在等待外部 API 回應期間不持有 SQLAlchemy `AsyncSession`（`ADR-0002`）
- [x] 端到端驗證 `READ` 與 `DRAFT` 工具免審批平行直通，而 `COMMIT` 工具強制進入 `WAITING_HITL` 並支援修改參數後送出（`TC-M2-01`, `TC-M2-02`）

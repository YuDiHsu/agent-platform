# 11: Admin 平台治理後台（帳號全生命週期與 Token 配額熔斷續傳、底層隱藏資產調優、公開上架審核、緊急煞車與資安稽核中心）

**What to build:** 建立專供平台管理員（`is_admin == true`）操作的 Web 治理後台（`/admin`）與後端管理 API（`/api/v1/admin/*`），讓所有平台級控管 100% 在網頁介面完成：
1. **使用者帳號全生命週期與 Token 額度熔斷續傳**：支援新增、編輯、停用（立即撤銷活躍連線）與刪除帳號（自動連帶銷毀私有資料與權杖、保留已發布至部門／全公司的公共資產，並禁止誤刪自己或最後一位管理員）。支援監控並設定每位使用者的 `token_quota_limit`；當使用者在對話或 DAG 中途超額時，工單與狀態機自動保存 Checkpoint 並暫停於 `PAUSED_QUOTA_EXCEEDED`，待管理員於後台調高額度或重置用量後，使用者可在**原對話視窗**一鍵無縫接續執行。
2. **公用與「使用者看不到的底層隱藏（`is_visible_to_user = false`）」資產調優與上架審核**：管理員可線上新增、編輯、熱更新共通與底層隱藏的 Rules、Skills、MCP / Tool Adapters 以及 7 大系統預設 Agent 範本（附無遮蔽完整 Prompt 測試沙盒），並審核員工申請公開至 `DEPARTMENT` / `GLOBAL` 的 `PENDING_REVIEW` 資產。
3. **全系統工單／排程緊急煞車、公共記憶管理、算力健康度與資安稽核日誌中心**：一鍵強制中止卡死工單或異常排程、清理 `ORG_GLOBAL` / `DEPARTMENT_SHARED` 記憶、檢視 SGLang/Embedding/DB/Redis/Sandbox 即時健康度與調整全域預設參數，並集中查詢與匯出 CLI 執行、HITL 與資安違規攔截日誌（`security_audit_logs`）。

**Blocked by:** 03: 洋蔥式規範隔離編譯器、兩階段漸進式技能與系統底層隱藏資產（is_visible_to_user=false）, 06: 可插拔 BaseToolAdapter 擴充接口、四大企業 MCP 連接器與高併發低延遲工具匯流排, 08: 個人獨立 Agent 工作區（自由增刪／開關預設與自建 Agent、一鍵 Reset 預設範本、三層記憶清理與公開上架送審）, 10: 24/7 背景排程常駐工作（Celery Heartbeats）、原子鎖定工單 Worker 與選配本機 Daemon

**Status:** ready-for-agent

- [ ] 帳號全生命週期管理（`GET/POST/PATCH/DELETE /api/v1/admin/users`）：支援新增帳號、調整部門／管理員權限／併發上限、停用帳號（立即阻斷推論並切斷活躍 WebSocket/Session）與刪除帳號（自動連帶清除該使用者的加密權杖、本機掛載、私有記憶、對話與私有 Agent，但保留其已公開至 `DEPARTMENT`/`GLOBAL` 的資產，且攔截刪除自己或最後一位管理員的操作）（`ADR-0004`）
- [ ] Token 額度熔斷與原對話無縫續傳（`PAUSED_QUOTA_EXCEEDED`）：每次推論原子累加 `users.tokens_consumed_total`；當達到 `token_quota_limit` 時，將進行中的 LangGraph 狀態存入 PostgreSQL Checkpoint、工單標記為 `PAUSED_QUOTA_EXCEEDED` 並推播額度暫停卡片；當管理員於後台調升該使用者額度或歸零用量後，使用者在**原對話視窗**點擊繼續即可從中斷的 DAG 步驟無縫接續完成，無須重開對話（`ADR-0004`）
- [ ] 底層隱藏資產（`is_visible_to_user = false`）與預設角色範本線上調優：管理員可在 `/admin/assets` 檢視、新增與修改所有 `is_visible_to_user = false` 的底層內建 Rules、Skills、MCP / Tool Adapters 與 7 大系統預設角色範本，提供無遮蔽的完整五層洋蔥 Prompt 預覽與測試沙盒，儲存後無須重啟即對全平台生效（`ADR-0004`）
- [ ] 公開資產上架審核佇列（`/admin/approvals`）：管理員可檢視所有 `approval_status == 'PENDING_REVIEW'` 的部門／全公司申請案，並執行「核准上架（`APPROVED`）」或「退回（`DRAFT`）」（`ADR-0004`）
- [ ] 全域任務緊急煞車、公共記憶管理與資安稽核中心（`/admin/operations` & `/admin/audit`）：支援強制中止任何卡死的 `IN_PROGRESS` 工單或暫停 24/7 排程、管理 `ORG_GLOBAL` 與 `DEPARTMENT_SHARED` 向量記憶、檢視 SGLang/Embedding/DB/Redis/Sandbox 連線健康度與動態修改系統預設配額，以及搜尋與匯出 `security_audit_logs` 與 `cli_execution_logs`（`ADR-0004`）

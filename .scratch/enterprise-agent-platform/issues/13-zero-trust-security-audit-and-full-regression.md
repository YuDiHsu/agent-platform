# 13: 多租戶／跨使用者零信任資安滲透稽核、多人高併發驗證與全平台回歸測試套件

**What to build:** 對全平台所有 API 端點、個人獨立工作區、資料庫查詢、跨 Worker WebSocket 反向 RPC 通道、OBO 權杖金庫、三層向量記憶檢索、系統底層隱藏資產（`is_visible_to_user = false`）與 Admin Generative BI 唯讀查詢執行全面的零信任資安滲透稽核與多人高併發壓力驗證，並完成涵蓋 `REQ-001` 至 `REQ-016` 及 `ADR-0001` 至 `ADR-0004` 的全平台端到端自動化回歸測試套件。

**Blocked by:** 08: 個人獨立 Agent 工作區（自由增刪／開關預設與自建 Agent、一鍵 Reset 預設範本、三層記憶清理與公開上架送審）, 10: 24/7 背景排程常駐工作（Celery Heartbeats）、原子鎖定工單 Worker 與選配本機 Daemon, 12: Admin 監控儀表板（5 大預設統計報表）與 AI 自然語言動態繪圖引擎（Generative BI Dashboard）

**Status:** ready-for-agent

- [ ] 跨帳號工作區與代理隔離驗證：驗證 User A 關閉、修改或刪除預設角色（如 `PM`）與自建 `PRIVATE` 代理、或執行一鍵 Reset 時，User B 的工作區與 Agent 清單 100% 不受影響；且 User B 無法讀取或呼叫 User A 的 `PRIVATE` 代理與非所屬部門的 `DEPARTMENT` 資產（`REQ-012`, `TC-M4-03`, `ADR-0003`）
- [ ] 底層隱藏資產與 Admin 權限邊界驗證：驗證一般使用者（`is_admin == false`）在所有 API 與 Studio 介面均 0% 洩漏 `is_visible_to_user = false` 的底層 Rules、Skills 與 MCP/Tools 內容，且呼叫任何 `/api/v1/admin/*` 端點均被 `403 Forbidden` 攔截並寫入 `security_audit_logs`（`ADR-0004`）
- [ ] Admin Generative BI 安全隔離驗證：驗證自然語言查 DB 引擎在面對惡意 Prompt 注入時，因受 PostgreSQL `READ ONLY` 交易與統計檢視表白名單保護，絕對無法修改資料表或讀取 `user_connector_tokens` 密文（`ADR-0004`）
- [ ] 跨帳號本機掛載、憑證與向量記憶隔離驗證：User B 無法存取 User A 的瀏覽器／Daemon 掛載、OBO 權杖、`hitl_approval_requests` 或 `USER_PRIVATE` / `EPHEMERAL_LOCAL_FILE` 記憶（達成 0 洩漏）（`REQ-012`, `TC-M4-03`）
- [ ] 多人同時在線高併發與跨登入狀態延續驗證：模擬多使用者同時發起含多工具平行呼叫之 DAG 對話、登出再登入還原 `PM` 進度、以及 Token 超額進入 `PAUSED_QUOTA_EXCEEDED` 後開通於原對話無縫續傳，加上 `TC-M1` ~ `TC-M5` 全套驗收測試 100% 通過（`ADR-0002`, `ADR-0003`, `ADR-0004`）

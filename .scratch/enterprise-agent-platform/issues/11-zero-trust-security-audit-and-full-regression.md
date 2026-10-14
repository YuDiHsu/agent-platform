# 11: 多租戶／跨使用者零信任資安滲透稽核與全平台端到端回歸驗證

**What to build:** 對全平台所有 API 端點、資料庫查詢、WebSocket 反向 RPC 通道、OBO 權杖金庫與三層向量記憶檢索執行全面的跨使用者與跨部門零信任資安稽核與加固，並完成涵蓋 `REQ-001` 至 `REQ-016`（`TC-M1-01` 至 `TC-M5-04`）的全平台自動化回歸測試套件。確保任何使用者（User B）在任何路徑下均無法讀取、列舉、呼叫或竄改另一位使用者（User A）的私有自建代理（`PRIVATE`）、部門專屬資源（不同部門之 `DEPARTMENT`）、個人加密連接器權杖、個人私有或暫時檔案切片記憶（`USER_PRIVATE` / `EPHEMERAL_LOCAL_FILE`）、本機掛載目錄或待審批的 HITL 請求。

**Blocked by:** 08: 自助式 Agent Studio、一句話 Meta-Prompt 生成器與本機掛載私有鎖定, 10: 24/7 背景排程常駐工作（Celery Heartbeats）、原子鎖定工單 Worker 與選配本機 Daemon

**Status:** ready-for-agent

- [ ] 跨帳號代理隔離驗證：User B 無法透過列表 API、直接 ID 查詢或 `ORCH` 動態路由檢索到 User A 的 `PRIVATE` 自建代理，亦無法存取非所屬部門的 `DEPARTMENT` 代理、規範與技能（`REQ-012`, `TC-M4-03`）
- [ ] 跨帳號本機掛載與 RPC 隔離驗證：User B 無法綁定、讀取、寫入或透過 WebSocket RPC 呼叫 User A 的瀏覽器掛載或 Local MCP Daemon（`REQ-012`, `TC-M4-03`）
- [ ] 跨帳號憑證與 HITL 隔離驗證：User B 無法解密或借用 User A 的 OBO 連接器權杖，亦無法對 User A 的 `hitl_approval_requests` 提交審批決策（`REQ-012`, `TC-M4-03`）
- [ ] 跨帳號向量記憶隔離驗證：向量記憶檢索嚴格過濾 `owner_user_id`、`department` 與 `session_id`，User A 的 `USER_PRIVATE` 與 `EPHEMERAL_LOCAL_FILE` 記憶對 User B 達成 0 洩漏（`REQ-012`, `TC-M4-03`）
- [ ] 全平台端到端驗收測試套件（`TC-M1-01` ~ `TC-M5-04`）全數自動化執行通過，且程式碼庫滿足零 `# TODO` 假實作、完整型別標註與 100% 商用友善開源授權規範

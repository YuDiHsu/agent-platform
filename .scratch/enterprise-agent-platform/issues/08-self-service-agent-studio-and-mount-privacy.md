# 08: 個人獨立 Agent 工作區（自由增刪／開關預設與自建 Agent、一鍵 Reset 預設範本、三層記憶清理與公開上架送審）

**What to build:** 打造每位使用者完全獨立且互不干擾的 Agent 工作區（User Workspace）與自助式 Agent Studio。每位使用者皆可在自己的工作區內：透過一句話 Meta-Prompt 自動生成並新增 Agent、直接編輯／開啟（`is_enabled=true`）／關閉（`is_enabled=false`）或刪除**任何 Agent（包含系統預設的 7 個角色範本 `ORCH`, `CEO`, `PM`, `FIN`, `SA`, `ARCH`, `SE`）**，且 User A 的任何增刪改或開關動作絕不影響 User B 的工作區。提供一鍵與指令 **`Reset`（`POST /api/v1/agents/presets/reset`）**，隨時從系統預設範本庫還原單一或全部預設 Agent；提供三種粒度的 Agent 記憶與歷史清理功能（按單一角色、按單一對話階段、按個人範圍清理）；並強制執行「綁定本機資料夾之 Agent 鎖定為 `PRIVATE`」與「發布至 `DEPARTMENT` / `GLOBAL` 之資產自動進入 `PENDING_REVIEW` 待管理員審核」規則。

**Blocked by:** 02: 多代理 DAG 任務編排、Claim-Check 產出物指標、跨登入工作階段持久化與斷點休眠工作區, 07: 跨 Worker Redis Pub/Sub 瀏覽器本機反向 RPC 橋接、記憶體文件解析與紅綠 Diff 寫入

**Status:** ready-for-agent

- [x] 建立 `user_agent_configs`（個人工作區角色狀態與覆寫表）並於 `agent_memories` 擴充 `role_code` 欄位：支援每位使用者獨立對任何 Agent（含系統預設 7 角色與自建角色）執行開啟／關閉（`is_enabled`）、修改設定或從個人工作區刪除，且完全不影響其他使用者（`ADR-0003`）
- [x] 提供一鍵與指令還原預設 Agent（`POST /api/v1/agents/presets/reset`，支援指定單一預設代碼如 `PM` 或全部 7 個預設角色）：呼叫後即從系統預設範本庫重新恢復該使用者工作區內的預設角色及其預設 Rules / Skills / Tools 綁定（`ADR-0003`）
- [x] 實作三層粒度記憶與歷史清理 API 與 UI 按鈕：（1）按特定角色清理記憶（`DELETE /api/v1/memories?role_code={code}`）；（2）刪除單一對話工作階段（`DELETE /api/v1/chat/sessions/{session_id}`，連同 Checkpoints 與暫時檔案切片）；（3）一鍵清空本人名下所有 `USER_PRIVATE` 與 `EPHEMERAL_LOCAL_FILE` 記憶；一般使用者禁止刪除 `DEPARTMENT_SHARED` 或 `ORG_GLOBAL` 公共記憶（`ADR-0003`）
- [x] Meta-Prompt 生成端點接收一句話描述，透過結構化推論回傳角色名稱、繁體中文 System Prompt、路由描述與推薦工具／規範／技能，建立時自動透過可配置 Embedding 客戶端計算 `routing_embedding`（`REQ-003`, `REQ-009`, `ADR-0001`）
- [x] 發布範圍與審核控管：建立 `PRIVATE` 資產立即生效；若一般使用者申請發布至 `DEPARTMENT` 或 `GLOBAL`，`approval_status` 自動設為 `PENDING_REVIEW` 等待管理員審核；若綁定本機資料夾（`bound_local_mount_id != null`）且嘗試設為 `DEPARTMENT` 或 `GLOBAL`，API 與 DB Check Constraint 強制攔截並回傳 `400 ERR_LOCAL_MOUNT_MUST_BE_PRIVATE`（`REQ-003`, `REQ-012`, `TC-M3-01`, `ADR-0004`）
- [x] 前端 Studio 左欄提供 4 步驟建立精靈（含工具／連接器勾選與本機資料夾綁定鎖定）、工作區角色清單開關／刪除／一鍵 Reset 按鈕，以及清理記憶控制項（`REQ-010`, `UI_SPEC.md`, `ADR-0003`）

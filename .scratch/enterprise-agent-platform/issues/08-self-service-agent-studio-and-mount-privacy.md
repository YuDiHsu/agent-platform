# 08: 自助式 Agent Studio、一句話 Meta-Prompt 生成器與本機掛載私有鎖定

**What to build:** 提供自助式 Agent Studio 介面與後端服務，讓一般員工只需輸入一句話描述想要的代理職責，即可由 Gemma 4 Meta-Prompt 輔助自動生成完整的角色系統提示詞（System Prompt）、路由描述（Routing Description）、JSON 輸出結構以及推薦綁定的規範與技能清單。使用者可在 Studio 中微調設定、綁定已授權的本機資料夾掛載，並選擇發布至個人私有（`PRIVATE`）、部門共享（`DEPARTMENT`）或全公司公開（`GLOBAL`）範圍，立刻納入 `ORCH` 的動態路由候選池中；同時在前端、API 與資料庫層強制執行「凡綁定本機資料夾之自建代理一律鎖定為 `PRIVATE`」的資安鐵律。

**Blocked by:** 02: 多代理 DAG 任務編排、Claim-Check 產出物指標與即時串流對話工作區, 07: 瀏覽器本機資料夾反向 RPC 橋接、記憶體文件解析與紅綠 Diff 寫入確認

**Status:** ready-for-agent

- [ ] Meta-Prompt 生成端點接收一句話自然語言描述，透過結構化推論回傳可直接填入表單的角色名稱、繁體中文 System Prompt、路由描述與推薦工具／規範／技能（`REQ-003`）
- [ ] 建立自建代理時自動透過可配置之 Embedding 客戶端計算 `routing_embedding`（維度依 `ADR-0001` 對齊 `settings.EMBEDDING_DIMENSION`），使其可立即被 `ORCH` 與動態路由檢索並指派工單（`REQ-003`, `REQ-009`, `ADR-0001`）
- [ ] 支援三層發布範圍（`PRIVATE`, `DEPARTMENT`, `GLOBAL`）：`PRIVATE` 僅建立者可見，`DEPARTMENT` 僅同部門可見，`GLOBAL` 全員可見（`REQ-003`, `REQ-012`）
- [ ] 當自建代理綁定任何本機資料夾（`bound_local_mount_id != null`）且嘗試將 `visibility_scope` 設為 `DEPARTMENT` 或 `GLOBAL` 時，API 必須攔截並回傳 `400 Bad Request`（錯誤碼 `ERR_LOCAL_MOUNT_MUST_BE_PRIVATE`），且資料庫 Check Constraint 同步強制保護（`REQ-003`, `REQ-012`, `TC-M3-01`）
- [ ] 前端 Studio 左欄提供 4 步驟視覺化建立精靈（Step 1：一句話 AI 自動生成規格並填入表單；Step 2：基本身分、匯報對象與發布範圍卡片；Step 3：勾選外部連接器與綁定本機資料夾，支援內嵌點擊「+ 新增掛載本機資料夾」直接呼叫瀏覽器授權；Step 4：規範與技能隔離綁定）；當在 Step 3 選擇綁定本機資料夾時，Step 2 的發布範圍自動鎖定為 `PRIVATE` 並顯示安全提示（`REQ-010`, `TC-M3-01`, `UI_SPEC.md`）

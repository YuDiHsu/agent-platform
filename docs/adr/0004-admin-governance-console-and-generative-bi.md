# 0004: 管理員治理後台、帳號與配額控管、底層隱藏資產及 AI 動態統計儀表板 (Generative BI)

Status: accepted

為使平台管理員能 100% 透過 Web 介面控管全平台帳號、資源配額、調優使用者不可見的底層資產，並即時掌握平台數據與安全狀態，我們決定：

1. **使用者帳號全生命週期管理與 Token 額度斷點續傳（`PAUSED_QUOTA_EXCEEDED`）**：管理員可於 `/admin/users` 新增、編輯（部門、職稱、`is_admin` 權限）、停用／啟用（停用時立即撤銷活躍連線）及刪除使用者帳號（刪除時連帶銷毀個人私密資料與私有代理，但保留已公開之 `DEPARTMENT` / `GLOBAL` 資產歸屬，並防呆禁止刪除自己或最後一位管理員）。當使用者於對話或 DAG 執行中途達到 `token_quota_limit` 上限時，系統將當前 LangGraph 狀態存入 PostgreSQL Checkpoint 並標記為 `PAUSED_QUOTA_EXCEEDED`；一旦管理員於後台調高額度或重置用量，使用者可在**同一個對話視窗**直接點擊繼續，從中斷步驟無縫接續執行。
2. **公開共通 vs. 系統底層隱藏資產（`is_visible_to_user = false`）与上架審核佇列（`PENDING_REVIEW`）**：在 `rules_registry`、`skills_registry` 與 `tools_registry` 新增 `is_visible_to_user` 欄位。設為 `false` 的底層內建資產在一般使用者的 API 與 Studio 介面完全隱藏且不可關閉，但由後端編譯器與工具匯流排強制載入；管理員可於 `/admin` 後台直接線上編輯、測試並熱更新這些底層資產與系統預設 Agent 範本。一般員工將自建資產發布至 `DEPARTMENT` 或 `GLOBAL` 時自動進入 `PENDING_REVIEW` 佇列，需經管理員審核通過方才公開。
3. **全系統工單／排程緊急煞車、共享記憶治理與資安稽核日誌中心**：管理員可於 `/admin` 強制中止卡死或失控的 DAG 工單與 24/7 Heartbeat 排程、管理 `ORG_GLOBAL` 與 `DEPARTMENT_SHARED` 向量記憶、檢視 SGLang／Embedding／DB／Redis／Sandbox 即時健康度並動態調整全域預設配額，以及查詢與匯出所有 CLI 執行、HITL 審批與資安違規攔截事件（`security_audit_logs`）。
4. **5 大預設監控報表與 AI 自然語言動態繪圖（Generative BI Dashboard）**：於 `/admin` 儀表板內建即時併發與健康度 KPI、部門與個人 Token 消耗排行、各角色利用率與延遲、Tool/Skill 呼叫與逾時率、HITL 資安攔截漏斗等 5 大預設報表；並提供 AI 數據分析搜尋列，由推論伺服器在 PostgreSQL 唯讀交易（`SET TRANSACTION READ ONLY` + 5s timeout）下執行安全參數化查詢，回傳結構化圖表 JSON（`GROUPED_BAR`, `LINE`, `PIE`, `DATA_TABLE`）與洞察摘要，直接在前端動態繪製跨週／跨人比較圖表並支援釘選。

# Enterprise Agent Hub

企業內網自建的多代理協作平台，由主代理將使用者需求拆解為跨角色有向無環圖（DAG）工單，協調內建專家角色與自建代理安全地讀寫本機檔案、呼叫外部連接器並產出專業交付物。

## 代理與編排 (Agents & Orchestration)

**Role (角色代理)**:
具備明確職責邊界、專屬系統提示詞與結構化輸出契約的專業代理（包含系統提供的 7 個預設角色範本 `ORCH`、`CEO`、`PM`、`FIN`、`SA`、`ARCH`、`SE` 以及使用者自建角色；每位使用者在個人獨立工作區內可自由新增、編輯、開啟、關閉或刪除任何角色，並可隨時透過重置指令一鍵還原預設角色範本）。
_Avoid_: Bot, assistant, hardcoded built-in role

**User Workspace (個人獨立工作區)**:
每位使用者專屬且互不干擾的執行環境，獨立保存該使用者的 Agent 清單與開關狀態、自訂規範／技能／工具偏好、對話工作階段與記憶，不會因其他使用者的增刪改而受影響。
_Avoid_: Shared global state, temporary browser state

**Master Orchestrator (`ORCH`, 主代理)**:
使用者唯一的總控對話入口，負責理解意圖、將跨領域需求拆解為任務有向無環圖（DAG）指派給各專業角色，並彙整最終結果。
_Avoid_: Router, controller

**Task Ticket (工單)**:
指派給單一角色執行的原子工作單元，具備上游目標繼承鏈（Goal Ancestry）、跳數上限（Max Hops）與執行狀態（`PENDING`、`IN_PROGRESS`、`WAITING_HITL`、`COMPLETED`、`FAILED`、`CIRCUIT_BROKEN`）。
_Avoid_: Job, subtask, thread

**Artifact (交付產出物)**:
角色完成工單後產出的完整專業文件、規格表、財務模型、架構圖或程式碼差異，以 Claim-Check 模式儲存，在對話狀態機中僅傳遞 200 字以內的摘要指標（Artifact Pointer）。
_Avoid_: Attachment, response text, blob

## 規範、技能與工具邊界 (Rules, Skills, Tools & MCP)

**Rule (規範)**:
約束角色行為、語氣、格式與資安紅線的宣告式守則（分為全公司強制 `GLOBAL_MANDATORY`、部門共享 `DEPARTMENT_SHARED` 與角色專屬 `ROLE_EXCLUSIVE`），僅編譯進系統提示詞，本身不執行任何外部動作。
_Avoid_: Policy, instruction, prompt template

**Skill (技能)**:
教導角色「如何完成特定專業領域任務」的兩階段標準作業程序（Stage-1 精簡目錄與 Stage-2 完整 SOP Markdown），可選配綁定受參數化保護的沙盒或本機 CLI 腳本。
_Avoid_: Plugin, macro, workflow

**Tool (工具)**:
角色透過結構化 Function Call 呼叫的原子外部或系統能力單元（如寄發信件、讀取檔案、搜尋訊息），具備嚴格的輸入參數結構與風險等級分類。
_Avoid_: Skill, action, command

**Tool Adapter (工具轉接器 / Connector)**:
將單一或一組同命名空間的 Tools 接入統一工具匯流排（Unified Tool Bus）的可插拔介面模組；只有當「角色被授權使用該工具」且「使用者個人勾選啟用」時，該工具才會對代理開放。
_Avoid_: Plugin, driver, wrapper

**MCP Server (模型上下文協定伺服器)**:
採用標準 Model Context Protocol 實作的一種 Tool Adapter（包含平台內建的 O365、Teams、Slack、通用信箱伺服器，以及後端動態註冊的遠端 MCP 服務與工程師選配的本機守護進程）。
_Avoid_: Tool, skill

## 資安、工作階段與記憶 (Security, Sessions & Memory)

**Action Tier (動作風險等級)**:
對所有 Tool 與 CLI 呼叫的三級風險分類：`READ`（純讀取，自動放行）、`DRAFT`（建立草稿，自動放行）與 `COMMIT`（對外發訊、寫入磁碟或變更系統，強制攔截並暫停等待人工審批）。
_Avoid_: Permission level, role scope

**HITL Approval Request (人工審批請求)**:
當代理觸發 `COMMIT` 等級動作時產生的待決策紀錄，將工單暫停於 `WAITING_HITL`，等待使用者本人核准（`APPROVED`）、修改參數後放行（`MODIFIED`）或拒絕（`REJECTED`）。
_Avoid_: Confirmation dialog, alert

**Local Workspace Mount (本機工作區掛載)**:
使用者透過瀏覽器原生檔案系統授權或本機守護進程綁定的個人電腦目錄，強制鎖定為本人私有（`PRIVATE`），禁止跨帳號存取。
_Avoid_: Shared drive, uploaded folder

**Chat Session (對話工作階段)**:
使用者與代理群進行協作的持久化工作空間，完整保存跨次登入的歷史對話訊息、各角色執行軌跡、DAG 進度、產出物指標與待審批狀態。
_Avoid_: Chat window, temporary thread

**Agent Memory (代理記憶)**:
供代理跨回合或跨工作階段檢索的向量化知識片段，分為個人私有（`USER_PRIVATE`）、部門共享（`DEPARTMENT_SHARED`）、全公司公開（`ORG_GLOBAL`）與本機大檔暫時切片（`EPHEMERAL_LOCAL_FILE`），支援由使用者按角色、工作階段或範圍主動清理。
_Avoid_: Context window, chat log, cache

## 平台治理與配額 (Platform Governance & Quotas)

**System-Internal Asset (系統底層隱藏資產)**:
由管理員於管理後台維護、在一般使用者介面完全隱藏（`is_visible_to_user = false`）但於後端強制載入生效的底層 Rule、Skill 或 MCP/Tool（例如資安防禦守則、系統內部調優 SOP），一般使用者無法檢視、修改或關閉。
_Avoid_: User-facing preset, hardcoded constant

**Token Quota (權杖額度配額)**:
管理員為每位使用者設定的推論 Token 消耗上限；當累計消耗達上限時，系統將進行中的對話斷點暫停於 `PAUSED_QUOTA_EXCEEDED`，待管理員調高額度或重置用量後，使用者可於原對話無縫接續執行。
_Avoid_: Rate limit, per-turn max_tokens

**Generative BI Widget (AI 動態生成式統計圖表)**:
管理員於監控儀表板輸入自然語言問題後，由推論伺服器轉換為唯讀安全資料庫查詢並輸出結構化圖表定義，直接在畫面上動態渲染出的互動式比較圖表與數據表。
_Avoid_: Static text reply, raw SQL console

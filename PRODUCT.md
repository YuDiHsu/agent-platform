# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

- **Frontend (`apps/web-portal`)**: Next.js 15 (App Router, TypeScript Strict Mode), React 19, TailwindCSS, Shadcn UI, Zustand, `@xyflow/react` (React Flow), `mermaid`, `react-diff-viewer-continued`, `lucide-react`, `idb-keyval`.
- **Backend & Orchestration (`apps/api-server`)**: Python 3.12, FastAPI (REST + SSE + WebSocket JSON-RPC 2.0), LangGraph (`langgraph-checkpoint-postgres`), SQLAlchemy 2.0 (`asyncpg`), Alembic, Celery + Redis 7, Docker SDK (rootless ephemeral CLI sandbox), `markitdown`, `jsonschema`.
- **On-Premise AI & Storage**: Local Google Gemma 4 (`gemma-4-27b-it`) served via SGLang / vLLM with FSM JSON Schema constrained decoding and RadixAttention KV-cache sharing; configurable OpenAI-compatible local Embedding model & vector dimension via `EMBEDDING_MODEL_NAME` and `EMBEDDING_DIMENSION` (e.g., `BAAI/bge-m3`, per `ADR-0001`); PostgreSQL 16 + `pgvector` (HNSW).

## Users

1. **企業知識工作者与部門專業人員（約 90% 使用者，涵蓋 PM、SA、財務、法務與管理層，首波試點如 `TS30` 與 `RD` 部門）**：
   - 在日常專案推進中需要跨領域協作（拆解訪談文件、撰寫規格、估算預算、排定時程、收發 O365 信件與 Teams/Slack 通知）。
   - 透過免安裝軟體的瀏覽器 Web Portal 或 Microsoft Teams Tab 直接掛載本機工作資料夾、檢視多代理產出物，並對外部寄信或本機檔案寫入進行人工審批（HITL）。
2. **資深研發工程師與架構師（約 10% 進階使用者，`SE` / `ARCH`）**：
   - 除使用 Web 工作區與自助式 Agent Studio 外，可選配執行輕量級 `Local MCP Daemon`，在關閉瀏覽器時仍支援 24/7 背景讀寫本機專案目錄及執行本機 Git / Pytest 診斷指令。
3. **行動端與跨裝置審批者（主管、外出專案經理與值班工程師）**：
   - 透過手機或平板瀏覽器／Teams 行動端接收背景排程（Heartbeats）晨報、檢視工單看板與產出物摘要，並即時處理 `WAITING_HITL` 人工審批請求。

## Product Purpose

打造 100% 企業機房自建落地、零機密外洩風險的多代理協作平台（**Enterprise Agent Hub**）。讓員工以自然語言向單一總控窗口（`ORCH`）發起複雜任務，自動拆解為有向無環圖（DAG）工單並調度 7 大內建專家角色（`ORCH`, `CEO`, `PM`, `FIN`, `SA`, `ARCH`, `SE`）與員工自建代理協同完成交付物；同時兼顧免安裝的本機檔案讀寫便利性與嚴格的零信任資安管控。

## Positioning

- **100% 商用友善開源與本地算力落地**：全線採用 MIT / Apache-2.0 / BSD-3 / PostgreSQL 授權技術棧（嚴格排除 AGPLv3、GPL、SSPL 或 Dify/n8n 等 Fair-code 限制），推論與向量檢索全數運行於企業內網 Gemma 4 與 PostgreSQL `pgvector`。
- **免安裝 Web-to-Local 反向 RPC 橋接**：結合 Chromium 原生 W3C File System Access API（`showDirectoryPicker` + IndexedDB 持久化）與雙向 WebSocket JSON-RPC 2.0，讓機房端代理直接讀寫員工授權的桌面資料夾，並於記憶體內以 `MarkItDown` 無狀態解析 `.docx` / `.xlsx` / `.pdf`。
- **針對本地模型最佳化的防崩潰編排**：透過 SGLang FSM 強制 100% 結構化 JSON 輸出、Claim-Check 200 字指標模式防止長文撐爆 Context、Top-5 動態 Tool RAG，以及最大化前綴快取命中率的五層洋蔥式提示詞編譯器（Onion Prompt Compiler）。
- **三級風險 HITL 閘門與雙目標防注入 CLI**：將所有動作分為 `READ`、`DRAFT`、`COMMIT`；凡外發郵件／訊息、寫入本機磁碟（強制紅綠 Diff 比對）或變更型 CLI 均自動觸發 LangGraph `NodeInterrupt` 暫停等待本人審批，且 CLI 一律經 JSON Schema 驗證與 `shlex.quote` 參數化跳脫。

## Operating Context

- **核心互動場景**：
  - **三欄式協作工作區（`/chat`）**：左側功能導覽、中央多代理對話流（含頂部即時迷你 DAG 進度列、角色徽章、Claim-Check 交付物摘要卡與內嵌 HITL 審批卡）、右側可收合多標籤工作台（`ARTIFACT` Markdown/Mermaid 預覽、`FILE_DIFF` 本機寫入紅綠比對、`TERMINAL_CLI` 沙盒與本機終端機輸出、`LIVE_DAG`）。
  - **組織拓撲圖與工單看板（`/org-chart`）**：切換檢視代理匯報階層圖與即時工單狀態／Token 預算消耗（`tokens_consumed / token_budget`）。
  - **自助式 Agent / Rule / Skill 工作坊（`/studio`）**：左欄 4 步驟視覺化建立精靈（含一句話 Meta-Prompt 自動生成）搭配右欄五層洋蔥式 Prompt 即時檢視器與測試沙盒。
  - **連接器與排程管理（`/settings/connectors`）**：管理個人 OBO 加密權杖（Microsoft 365、Teams、Slack、通用 IMAP/SMTP）、本機掛載資料夾與 24/7 Celery 背景排程。
- **瀏覽器與執行環境差異**：
  - 桌面端 Chrome / Microsoft Edge 支援完整原生本機資料夾掛載；在行動端或不支援 `showDirectoryPicker` 的瀏覽器上，介面須提供清楚的唯讀／雲端連接器替代指引或引導改由已連線之 `Local MCP Daemon` 執行。

## Capabilities and Constraints

- **7 大內建角色與職責邊界**：
  - `ORCH`（主代理）：唯一對話入口、DAG 拆解（單次規劃上限 6 步，系統硬上限 `max_hops = 8`）與最終彙整；嚴禁自行撰寫規格、架構圖、程式碼或財務報表。
  - `CEO`（執行長決策代理）：產出 `STRATEGY_MEMO`（Go / Conditional Go / No-Go 與分階段放行條件）。
  - `PM`（專案經理）：產出 `PROJECT_PLAN_WBS`，並操作 O365 信箱／行事曆、Teams 與 Slack。
  - `FIN`（財務專家）：產出 `FINANCIAL_MODEL`，預設新台幣（`NT$`）、36 個月硬體直線折舊與保守／基準／樂觀三情境 ROI 試算表。
  - `SA`（系統分析師）：產出 `REQUIREMENT_SPEC`（功能編號、Given/When/Then 驗收條件、資料字典與 OpenAPI 3.1 契約）。
  - `ARCH`（架構分析師）：產出 `ARCH_DIAGRAM`（ADR 與 Mermaid 架構／時序圖）。
  - `SE`（資深工程師）：產出 `CODE_DIFF`（具備完整型別與測試的生產級實作，零 `# TODO` 假實作）。
- **不可妥協的資安與隔離鐵律**：
  - **本機掛載私有鎖定（`ERR_LOCAL_MOUNT_MUST_BE_PRIVATE`）**：凡綁定本機資料夾（`bound_local_mount_id != null`）的自建代理，在 UI、API 與資料庫 Check Constraint 三層強制鎖定 `visibility_scope = 'PRIVATE'`，嚴禁跨使用者存取。
  - **路徑與指令防護**：前後端雙重阻擋路徑穿越（`..`）與敏感檔案（`.env`, `.pem`, `.pfx`, `id_rsa`, `.git/`, `node_modules/`）；CLI 嚴禁拼接原始字串，Server Sandbox 容器強制無網路（`network_mode="none"`）、唯讀根目錄、`512m` 記憶體與 `pids_limit=64`。
  - **規則與憑證隔離**：`ROLE_EXCLUSIVE` 規則絕不跨角色外洩；個人 OAuth2 OBO 權杖以每筆獨立 Nonce 的 AES-256-GCM 加密儲存，且向量記憶嚴格過濾擁有者與部門範圍。

## Brand Commitments

- **產品名稱**：`Enterprise Agent Hub`（企業多代理協作平台）。
- **語言與語氣規範（`RULE_GLOBAL_ZH_TW`）**：全介面、代理輸出、錯誤提示與技術文件一律使用**繁體中文（`zh-TW`）**與台灣資訊產業慣用術語（例如：`專案`、`資料庫`、`非同步`、`伺服器`、`權杖`、`資料表`、`腳本`），避免中國大陸慣用詞彙，語氣專業、精準、可稽核。

## Evidence on Hand

- **核心架構與實作規格**：`MASTER_SPEC.md`（`EAMP-MASTER-SPEC-2026-V3.0`）。
- **前端互動與狀態機規格**：`UI_SPEC.md`（`EAMP-UI-SPEC-2026-V3.0`）。
- **內建角色提示詞與 Few-Shot 範例種子**：`packages/builtin-roles/seed_roles.yaml`。
- **縱切實作工單圖（Ticket Graph）**：`.scratch/enterprise-agent-platform/issues/01-*.md` 至 `11-*.md`。
- **尚未提供的素材（禁止憑空捏造）**：目前無真實客戶證言、外部公開行銷數據或正式企業商標圖檔；所有範例與測試資料均以內部試點情境呈現。

## Product Principles

1. **人類掌舵的零信任自動化（Human-in-the-Loop by Construction）**：讀取與草稿可全速自動化，但任何對外發訊、修改本機磁碟或執行變更型指令的 `COMMIT` 動作，都必須將控制權與清楚的 Diff／參數預覽交還給使用者本人拍板。
2. **摘要在對話、細節在工作台（Claim-Check Progressive Clarity）**：對話流保持精煉易讀，只呈現角色交接狀態与 200 字關鍵結論；完整的規格表、Mermaid 架構圖、紅綠 Diff 與終端機日誌一律在右側工作台結構化展開。
3. **嚴格的職責與知識邊界（Strict Role & Context Isolation）**：每個角色只做符合其專業授權的事、只載入屬於自己的專屬規範與當前啟用的技能 SOP，讓決策鏈透明且可追蹤。
4. **零安裝門檻、漸進式進階能力（Zero-Install First, Power-User Ready）**：一般員工打開瀏覽器就能安全掛載本機資料夾與使用沙盒工具，工程師則可無縫掛載本機 Daemon 擴充離線與 CLI 能力。

## Accessibility & Inclusion

- **無障礙標準（WCAG 2.1 AA）**：
  - 確保深色與淺色自適應主題（Dark / Light Adaptive Shell）下的文字、角色徽章與狀態色標（`COMPLETED`、`IN_PROGRESS`、`WAITING_HITL`、`FAILED`）皆符合 WCAG AA 對比度要求，且狀態不單靠顏色區分（必須同時搭配圖示與狀態文字標籤）。
  - 完整支援鍵盤導覽（Keyboard Navigation）、清楚的 Focus Ring、對話串流與 HITL 審批通知的 `aria-live` 語意宣告，以及 Modal／抽屜的 Focus Trap 與 `Esc` 關閉支援。
- **跨裝置與行動端響應式支援（Responsive Desktop & Mobile Adaptation）**：
  - 桌面端呈現完整三欄式（左導覽、中舞台、右可調整寬度工作台）佈局；在平板與行動裝置小螢幕上，左側導覽與右側產出物／Diff／終端機工作台須平滑收合為底部或側邊抽屜（Drawer / Sheet），確保外出人員在手機上也能順暢閱讀產出物與點擊 HITL 核准／修改／拒絕按鈕。
  - 當在行動端或不支援 File System Access API 的瀏覽器操作時，本機資料夾掛載控制項須提供明確的環境限制提示與替代操作路徑，不得發生無反應或腳本崩潰。

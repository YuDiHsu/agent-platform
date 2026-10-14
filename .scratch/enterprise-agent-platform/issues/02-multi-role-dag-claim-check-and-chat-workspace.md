# 02: 多代理 DAG 任務編排、Claim-Check 產出物指標、跨登入工作階段持久化與斷點休眠工作區

**What to build:** 讓使用者能在三欄式 Web 對話工作區輸入自然語言需求，由主代理（`ORCH`）理解意圖並決定直接回覆（`DIRECT_ANSWER`）或拆解為跨角色的任務有向無環圖（`DELEGATE_DAG`）。編排引擎依拓撲順序與平行依賴關係派發工單給各專業子代理（如先由 `SA` 拆解需求，再平行交由 `ARCH` 與 `FIN` 設計架構與試算成本，最後由 `PM` 彙整），且執行與瀏覽器連線脫鉤（使用者關閉 App 或登出後仍繼續執行）。當等待人工審批或等待離線瀏覽器時，狀態寫入 PostgreSQL Checkpoint 後立即釋放 Worker（Checkpoint Hibernation，0% 待機負載）。所有對話氣泡、角色切換、DAG 進度與產出物皆持久化於 `chat_sessions` 與 `chat_messages`，確保使用者隔天重新登入時透過 Bootstrap API 100% 還原上次的歷史紀錄與角色執行狀態。

**Blocked by:** 01: 平台最小可行骨架、13 表資料庫遷移與內建角色/規範/技能種子載入

**Status:** ready-for-agent

- [ ] 新增增量資料庫遷移以建立 `chat_sessions` 與 `chat_messages` 表，持久化每次對話階段、所有角色訊息氣泡、工具呼叫事件與 DAG 步驟狀態（`ADR-0002`, `ADR-0003`）
- [ ] `ORCH` 可將跨領域需求拆解為具備 `depends_on_steps` 的無環任務圖（DAG），隨工單傳遞濃縮的最高指導目標（Goal Ancestry），並支援 `max_hops = 8` 硬性斷路器（超過上限自動中止並標記為 `CIRCUIT_BROKEN`）（`REQ-001`, `REQ-002`, `TC-M1-02`）
- [ ] 實作與瀏覽器斷線脫鉤的背景執行與「零待機休眠（Checkpoint Hibernation）」：當工單進入等待狀態（如 `WAITING_HITL`、`WAITING_BROWSER` 或 `PAUSED_QUOTA_EXCEEDED`）時，狀態存入 PostgreSQL Checkpoint 後立即釋放協程與資料庫連線（佔用 0% CPU/RAM），並限制每位使用者同時處於 `IN_PROGRESS` 的併發工單配額（`ADR-0002`, `ADR-0003`）
- [ ] 提供 `GET /api/v1/users/me/bootstrap` 與 `GET /api/v1/chat/sessions/{session_id}/state`：當使用者呼叫 `PM` 做事後關閉 App，隔天重新登入時，前端 `useWorkspaceStore` 自動還原完整的歷史對話、頂部 DAG 進度列、`PM` 的最新執行狀態、產出物與待審批卡片（`ADR-0002`, `ADR-0003`）
- [ ] 子代理完成任務時，完整長文內容寫入 `shared_artifacts`，狀態機僅保留含 `artifact_id`、標題、類別與 200 字內摘要的 Claim-Check 指標（`REQ-008`, `ADR-002`）
- [ ] 對話串流端點透過 SSE 依序推播 `orchestrator_plan`、`role_switched`、`artifact_created` 與 `final_response` 事件，並在等待推論或外部 I/O 期間釋放 SQLAlchemy `AsyncSession`（`REQ-010`, `ADR-0002`）
- [ ] 前端提供三欄式自適應應用殼層與全域 Zustand 狀態機：收到 `orchestrator_plan` 時自動展開右側 `LIVE_DAG` 分頁並更新頂部橫向迷你 DAG 進度列；收到 `artifact_created` 時自動展開右側 `ARTIFACT` 分頁渲染 Markdown 與可縮放平移的 Mermaid 圖表（`REQ-010`, `UI_SPEC.md`）
- [ ] 組織圖頁面支援切換「代理組織拓撲圖（React Flow）」與「工單看板與 Token 追蹤」雙視圖，點擊任一角色節點（如 `PM`）可展開側邊抽屜檢視該角色跨日期的歷史工單、Token 消耗進度與已綁定技能（`REQ-010`, `UI_SPEC.md`, `ADR-0003`）
- [ ] 符合 `PRODUCT.md` 無障礙（WCAG 2.1 AA）與跨裝置響應式規範：深淺色主題對比度達標、狀態徽章同時具備圖示與文字標籤、支援完整鍵盤導覽與 `aria-live` 串流宣告；在行動端與小螢幕下，左側導覽與右側工作台自動收合為側邊／底部抽屜（Drawer / Sheet）（`PRODUCT.md`）

# 02: 多代理 DAG 任務編排、Claim-Check 產出物指標與即時串流對話工作區

**What to build:** 讓使用者能在雙欄式 Web 對話工作區輸入自然語言需求，由主代理（`ORCH`）理解意圖並決定直接回覆（`DIRECT_ANSWER`）或拆解為跨角色的任務有向無環圖（`DELEGATE_DAG`）。編排引擎依拓撲順序與平行依賴關係派發工單給各專業子代理（如先由 `SA` 拆解需求，再平行交由 `ARCH` 與 `FIN` 設計架構與試算成本，最後由 `PM` 彙整），並透過 SSE 即時向前端推播編排計畫、角色切換、產出物建立與最終綜合報告。子代理產出的完整 Markdown 與 Mermaid 圖表存入資料庫產出物表，狀態機內僅傳遞 200 字以內的輕量指標（Claim-Check 模式）以保護本地模型 Context Window；使用者可在工作區右側即時預覽交付物，並於組織圖與看板頁面檢視角色層級與工單執行狀態。

**Blocked by:** 01: 平台最小可行骨架、13 表資料庫遷移與內建角色/規範/技能種子載入

**Status:** ready-for-agent

- [ ] `ORCH` 可將跨領域需求拆解為具備 `depends_on_steps` 的無環任務圖（DAG），並隨工單傳遞濃縮的最高指導目標（Goal Ancestry）（`REQ-001`, `REQ-002`）
- [ ] 狀態機支援依拓撲順序執行無前置依賴或已完成前置依賴的子任務，並在 PostgreSQL 持久化執行斷點（Checkpoints）
- [ ] 實作 `max_hops = 8` 硬性斷路器：當單次對話跨角色流轉次數超過上限時自動中止並標記工單為 `CIRCUIT_BROKEN`（`REQ-002`, `TC-M1-02`）
- [ ] 子代理完成任務時，完整長文內容寫入產出物儲存區，狀態機僅保留含 `artifact_id`、標題、類別與 200 字內摘要的指標（`REQ-008`, `ADR-002`）
- [ ] 對話串流端點透過 SSE 依序推播 `orchestrator_plan`、`role_switched`、`artifact_created` 與 `final_response` 事件（`REQ-010`）
- [ ] 前端提供三欄式自適應應用殼層（左側導覽列、中央主舞台、右側可收合多標籤工作區）與全域 Zustand 狀態機：收到 `orchestrator_plan` 時自動展開右側 `LIVE_DAG` 分頁並更新頂部橫向迷你 DAG 進度列（依 `COMPLETED` / `IN_PROGRESS` / `WAITING_HITL` / `PENDING` 變換色標）；收到 `artifact_created` 時自動展開右側 `ARTIFACT` 分頁（`REQ-010`, `UI_SPEC.md`）
- [ ] 對話氣泡顯示 7 大角色專屬色彩徽章，並將長篇交付物濃縮為內嵌 Claim-Check 摘要卡片（顯示標題與 200 字摘要，點擊按鈕即於右側工作區開啟完整 Markdown 表格與可縮放平移的 Mermaid 圖表，並支援匯出 `.md`）（`REQ-010`, `TC-M1-02`, `UI_SPEC.md`）
- [ ] 組織圖頁面支援切換「代理組織拓撲圖（React Flow）」與「工單看板與 Token 追蹤」雙視圖，點擊任一角色節點可展開側邊抽屜檢視該角色的近期工單、Token 消耗進度（`tokens_consumed / token_budget`）與已綁定技能（`REQ-010`, `UI_SPEC.md`）
- [ ] 符合 `PRODUCT.md` 無障礙（WCAG 2.1 AA）與跨裝置響應式規範：深淺色主題對比度達標、狀態徽章同時具備圖示與文字標籤、支援完整鍵盤導覽與 `aria-live` 串流宣告；在行動端與小螢幕下，左側導覽與右側工作台自動收合為側邊／底部抽屜（Drawer / Sheet）（`PRODUCT.md`）

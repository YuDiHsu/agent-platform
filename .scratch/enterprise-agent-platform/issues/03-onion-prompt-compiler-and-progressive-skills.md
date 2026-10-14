# 03: 洋蔥式規範隔離編譯器、兩階段漸進式技能與系統底層隱藏資產（is_visible_to_user=false）

**What to build:** 為每個角色代理提供嚴格隔離且對 SGLang RadixAttention 前綴快取友善的洋蔥式 System Prompt 編譯機制、兩階段漸進式技能（Progressive-Disclosure Skills）載入，以及區分「使用者可見資產」與「使用者看不到的系統底層隱藏資產（`is_visible_to_user = false`）」。每次角色執行時，系統固定依「Layer 1: 全公司與部門共通強制規範（含底層隱藏規範） -> Layer 2: 角色核心職責 Prompt -> Layer 3: 該角色專屬規範 -> Layer 4: 第一階段可用技能精簡清單 -> Layer 5: 第二階段已啟用技能完整 SOP -> Layer 6: 當前回合動態篩選之 Top-5 工具 Schema（置於最尾端以保護前綴快取）」順序組裝提示詞。設為 `is_visible_to_user = false` 的內建底層規範與技能在後端強制載入生效，但在一般使用者的 API 與前端 Studio（含洋蔥式 Prompt 預覽器）中 100% 隱藏且不可關閉。

**Blocked by:** 01: 平台最小可行骨架、13 表資料庫遷移與內建角色/規範/技能種子載入, 02: 多代理 DAG 任務編排、Claim-Check 產出物指標、跨登入工作階段持久化與斷點休眠工作區

**Status:** ready-for-agent

- [ ] 擴充 `rules_registry` 與 `skills_registry` 支援 `is_visible_to_user`（預設 `true`）與 `approval_status` 欄位（`ADR-0004`）
- [ ] 洋蔥式編譯器固定以 `GLOBAL_MANDATORY` 與當前使用者所屬部門之 `DEPARTMENT_SHARED` 規範作為最外層靜態前綴（依 `priority` 與 `code` 確定性排序），並將動態工具定義固定置於最外層尾端（Layer 6），確保多人同時在線時 Layer 1~4 的 SGLang KV Cache 前綴 100% 共享（`REQ-013`, `ADR-003`, `ADR-0002`）
- [ ] 嚴格隔離角色專屬規範：`SA` 編譯後的提示詞包含全公司規範與 `RULE_SA_OPENAPI_AND_ERD`，且 0% 包含 `FIN` 或 `SE` 的專屬規範（`TC-M5-01`）
- [ ] 系統底層隱藏保護：設為 `is_visible_to_user = false` 的底層 Rules 與 Skills 在後端編譯時強制載入，但一般使用者的查詢 API（`GET /api/v1/rules`, `GET /api/v1/skills`）與前端 Studio 的洋蔥式 Prompt 檢視器完全過濾遮蔽，防止一般使用者窺探或關閉底層守則（`ADR-0004`）
- [ ] 第一階段技能目錄每項待命技能僅注入精簡描述（低於 60 tokens）；當代理呼叫 `activate_skill` 後，下一輪編譯動態掛載第二階段完整 SOP 與 CLI 呼叫指引，並透過 SSE 推播 `skill_activated` 事件（`REQ-014`, `TC-M5-02`）
- [ ] 提供規範與技能的 CRUD API 與角色 M:N 綁定管理，並在前端 Studio 提供規範綁定選擇器、技能編輯視窗與「洋蔥式 Prompt 即時檢視器與測試沙盒」（`REQ-013`, `REQ-014`, `UI_SPEC.md`）

# 03: 洋蔥式規範隔離編譯器（Onion Prompt Compiler）與兩階段漸進式技能載入

**What to build:** 為每個角色代理提供嚴格隔離且對 SGLang RadixAttention 前綴快取友善的洋蔥式 System Prompt 編譯機制，以及兩階段漸進式技能（Progressive-Disclosure Skills）載入與管理介面。每次角色執行時，系統固定依「全公司與部門共通強制規範 -> 角色核心職責 Prompt -> 該角色專屬規範 -> 第一階段可用技能精簡清單 -> 第二階段已啟用技能完整 SOP」順序組裝提示詞，確保綁定給角色 A 的專屬規範絕不洩漏至角色 B；待命中的技能僅注入名稱與觸發說明，唯有當代理主動呼叫 `activate_skill` 或設為自動啟用時才載入完整 SOP 與 CLI 參數結構。同時在前端 Studio 與後端提供規範、技能與角色綁定的查詢、新增與管理功能。

**Blocked by:** 01: 平台最小可行骨架、13 表資料庫遷移與內建角色/規範/技能種子載入, 02: 多代理 DAG 任務編排、Claim-Check 產出物指標與即時串流對話工作區

**Status:** ready-for-agent

- [ ] 洋蔥式編譯器固定以 `GLOBAL_MANDATORY` 與當前使用者所屬部門之 `DEPARTMENT_SHARED` 規範作為最外層前綴（依 `priority` 與 `code` 確定性排序），最大化推論引擎 KV Cache 命中率（`REQ-013`, `ADR-003`）
- [ ] 嚴格隔離角色專屬規範：`SA` 編譯後的提示詞包含全公司規範與 `RULE_SA_OPENAPI_AND_ERD`，且 0% 包含 `FIN` 或 `SE` 的專屬規範（`TC-M5-01`）
- [ ] 第一階段技能目錄每項待命技能僅注入精簡描述（低於 60 tokens），不載入完整 SOP 內文（`REQ-014`, `TC-M5-02`）
- [ ] 當代理於工具呼叫中執行 `activate_skill` 並指定已綁定之技能代碼後，狀態機記錄該角色已啟用技能，下一輪編譯即動態掛載第二階段完整 SOP 與 CLI 呼叫指引，並透過 SSE 推播 `skill_activated` 事件（`TC-M5-02`）
- [ ] 提供規範與技能的 CRUD API 與角色 M:N 綁定管理，並在前端 Studio 提供規範綁定選擇器（鎖定顯示自動繼承之 `GLOBAL_MANDATORY` 規範，並供勾選專屬規範與技能）與技能新增／編輯視窗（`REQ-013`, `REQ-014`, `UI_SPEC.md`）
- [ ] 前端 Studio 右側提供「洋蔥式 Prompt 即時檢視器與測試沙盒（Live Prompt Onion Inspector）」，以分層色標預覽當前角色的編譯後提示詞（Layer 1 全公司與部門規範、Layer 2 角色核心 Prompt、Layer 3 角色專屬隔離規範、Layer 4 第一階段精簡技能清單），並支援在儲存前直接發送測試訊息驗證輸出（`UI_SPEC.md`）

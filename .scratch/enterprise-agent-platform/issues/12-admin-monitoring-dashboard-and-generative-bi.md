# 12: Admin 監控儀表板（5 大預設統計報表）與 AI 自然語言動態繪圖引擎（Generative BI Dashboard）

**What to build:** 在 `/admin/dashboard` 打造管理員專屬的數據監控儀表板，內建 **5 大互動式統計報表**（即時併發與健康度 KPI 列、部門與個人 Token 消耗排行與額度預警、各角色代理利用率與延遲分析、Skill / Tool / MCP 呼叫量與逾時錯誤率排行、HITL 資安攔截審批漏斗），並在儀表板頂部內建 **「AI 數據分析師（Ask Dashboard AI — Generative BI）」**。管理員只需輸入自然語言問題（例如：「*幫我比較使用者王小明上週跟這週的 Token 花費與各角色呼叫次數*」），後端即透過推論伺服器（SGLang Gemma 4）將問題轉為安全的唯讀資料庫查詢，撈出真實統計數據後以結構化 JSON Schema 回傳文字洞察與圖表定義，直接在 Dashboard 畫面上動態渲染出互動式比較圖表（並排長條圖、趨勢折線圖、圓餅圖或數據表），且支援一鍵釘選（Pin）為儀表板常駐報表。

**Blocked by:** 11: Admin 平台治理後台（帳號全生命週期與 Token 配額熔斷續傳、底層隱藏資產調優、公開上架審核、緊急煞車與資安稽核中心）

**Status:** ready-for-agent

- [ ] 實作 `/api/v1/admin/analytics/overview` 與前端 5 大預設統計報表：（1）即時同時在線人數、執行中工單、待審批數、今日總 Token 與超額預警 KPI 卡；（2）支援日／週／月切換之部門與個人 Token 消耗趨勢及額度使用率排行榜；（3）各角色代理（`ORCH`, `SA`, `ARCH`, `PM`, `FIN`, `SE`, `CEO` 與自建角色）派工次數、平均耗時、Token 佔比與斷路器觸發率；（4）各 Tool Adapter / MCP / Skill 呼叫次數、平均延遲（`ms`）與 Timeout／錯誤率排行；（5）HITL `COMMIT` 攔截總數與 `APPROVED` / `MODIFIED` / `REJECTED` 比例圖（`ADR-0004`）
- [ ] 實作 AI 自然語言唯讀安全查詢引擎（`POST /api/v1/admin/analytics/ask`）：僅限 `is_admin == true` 呼叫；將自然語言問題轉為針對安全統計檢視表的參數化 `SELECT` 查詢，強制在 PostgreSQL **唯讀交易（`SET TRANSACTION READ ONLY` + `SET LOCAL statement_timeout = '5000ms'`）** 中執行，嚴格禁止任何 `INSERT/UPDATE/DELETE/DROP` 語句，並完全隔離加密權杖（`encrypted_access_token`）與密碼雜湊欄位（`ADR-0004`）
- [ ] 結構化圖表生成與前端動態渲染（Generative BI Canvas）：推論伺服器透過 SGLang FSM 強制輸出符合 `AdminBIChartResponse` Schema 的 JSON（含 `insight_markdown`、`chart_type` 如 `'GROUPED_BAR'` | `'LINE'` | `'PIE'` | `'STACKED_BAR'` | `'DATA_TABLE'`、`x_axis_key`、`series` 與 `dataset`）；前端收到後直接以互動式圖表元件畫出跨週期／跨使用者比較圖表（支援切換圖表型態與匯出 CSV），而非僅回覆純文字（`ADR-0004`）
- [ ] 支援常駐報表釘選（`POST / DELETE /api/v1/admin/analytics/pins`）：管理員可將 AI 動態生成的比較圖表一鍵釘選至 `admin_pinned_widgets` 表，下次開啟 `/admin/dashboard` 時自動載入並重新整理最新數據（`ADR-0004`）

# 05: HITL 人工審批安全閘門（READ / DRAFT / COMMIT）與狀態機斷點續傳

**What to build:** 在統一工具與 CLI 執行路徑前建立三級風險人工審批閘門（HITL Security Gate）。系統將所有工具與技能 CLI 操作分類為 `READ`、`DRAFT` 與 `COMMIT`：`READ` 與 `DRAFT` 操作直接放行執行；凡屬 `COMMIT` 等級（如實際寄出郵件、發送群組訊息、寫入本機檔案、執行變更型 CLI）皆自動攔截，於資料庫建立待審批請求、將工單狀態切換為 `WAITING_HITL`，並觸發 LangGraph 斷點中斷（Interrupt）暫停執行。前端對話工作區即時渲染互動式 HITL 審批卡片，預覽預計執行的目標與參數；使用者可選擇「核准（`APPROVED`）」、「修改參數後放行（`MODIFIED`）」或「拒絕（`REJECTED`）」，後端隨即喚醒暫停的 Checkpoint 並依使用者決策繼續或中止操作。

**Blocked by:** 02: 多代理 DAG 任務編排、Claim-Check 產出物指標與即時串流對話工作區

**Status:** ready-for-agent

- [ ] 攔截器依據權限矩陣判別操作等級：`READ` 與 `DRAFT` 等級工具自動執行且不暫停狀態機（`REQ-007`, `TC-M2-01`）
- [ ] 當代理呼叫 `COMMIT` 等級操作時，系統寫入一筆狀態為 `PENDING` 的審批紀錄、透過 SSE 推播 `hitl_required` 事件，並暫停該回合 LangGraph 狀態機於 `WAITING_HITL`（`REQ-007`, `TC-M2-02`）
- [ ] 審批決策端點支援 `APPROVED`、`MODIFIED`（附帶 `user_modified_payload`）與 `REJECTED` 三種決策，且僅允許該審批單所屬的使用者本人提交決策（`REQ-007`, `REQ-012`）
- [ ] 當使用者提交 `MODIFIED` 並修改參數（例如更改收件人或信件內文）時，喚醒後的狀態機確實使用修改後的參數執行工具，而非原始提議參數（`TC-M2-02`）
- [ ] 當使用者提交 `REJECTED` 時，系統取消該次工具呼叫並將拒絕原因回饋給角色代理以妥善收尾
- [ ] 前端於對話流內嵌及頂部導覽列通知抽屜同步呈現 HITL 審批卡片（顯示執行角色、工具名稱、執行目標徽章與可展開的參數預覽），提供「核准執行」、「在右側修改內容後執行」（連動右側工作區開啟可編輯表單並送出 `MODIFIED`）與「拒絕並退回 Agent」三顆操作按鈕，且頂部迷你 DAG 進度列同步將該步驟標示為琥珀色 `WAITING_HITL` 狀態（`REQ-010`, `UI_SPEC.md`）

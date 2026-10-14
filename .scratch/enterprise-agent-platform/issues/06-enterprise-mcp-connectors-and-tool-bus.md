# 06: 企業內部 MCP 連接器（O365、Teams、Slack、通用信箱）與統一工具匯流排

**What to build:** 實作企業內部四大標準化 MCP 連接器伺服器（Microsoft Office 365、Microsoft Teams、Slack 與通用 IMAP/SMTP 信箱）並掛載至統一工具執行匯流排（Unified Tool Bus）。當角色代理（如 `PM` 或 `SA`）被授權對應的命名空間時，可透過使用者本人的解密 OBO 權杖執行搜尋信件、建立 Outlook 草稿、發送正式信件、查詢會議室與人員空檔、建立行事曆事件、讀取 OneDrive 檔案、讀取與發送 Teams／Slack 頻道訊息，以及發送 Teams Adaptive Approval Cards；所有讀取與草稿操作自動完成，所有外發信件、行事曆邀請與群組發文則自動經過 HITL 審批閘門確認後才實際送出。

**Blocked by:** 04: 個人 OBO 權杖加密金庫（AES-256-GCM）與動態角色／工具向量檢索（Tool RAG）, 05: HITL 人工審批安全閘門（READ / DRAFT / COMMIT）與狀態機斷點續傳

**Status:** ready-for-agent

- [ ] Microsoft 365 MCP 連接器支援透過使用者 OBO 權杖執行信件搜尋（`READ`）、建立草稿（`DRAFT`）、寄出信件（`COMMIT`）、尋找會議空檔（`READ`）、建立行事曆會議（`COMMIT`）與讀取 OneDrive 檔案（`READ`）（`REQ-006`, `TC-M2-01`）
- [ ] Microsoft Teams MCP 連接器支援讀取授權頻道討論串（`READ`）、發送頻道／個人訊息（`COMMIT`）與推播 HITL Adaptive Approval Cards（`REQ-006`, `REQ-007`）
- [ ] Slack 與通用信箱 MCP 連接器支援頻道訊息搜尋與發文、IMAP 未讀信件搜尋及 SMTP 信件寄送（`REQ-006`）
- [ ] 統一工具匯流排（Unified Tool Bus）驗證呼叫角色之 `allowed_tool_namespaces` 權限，防止未授權角色呼叫不屬於其職責的外部連接器
- [ ] 端到端驗證 `o365_search_messages` 與 `o365_create_draft` 免審批直通，而 `o365_send_mail`、`o365_create_event`、`teams_send_message` 與 `slack_post_message` 強制進入 `WAITING_HITL` 並支援修改參數後送出（`TC-M2-01`, `TC-M2-02`）

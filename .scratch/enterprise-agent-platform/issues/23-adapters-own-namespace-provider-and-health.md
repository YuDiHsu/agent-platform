# 23: Adapter 自持 namespace、provider 與健康檢查（審查後續：06）

**What to build:** 工具匯流排向 Adapter 本身詢問它的 namespace 與 OBO 權杖 provider，而非另外維護一份字串前綴對照；Adapter 宣告的 `provider` 終於被使用。`health_check()` 有實際用途：Admin 掛載遠端 MCP／Webhook 時先檢查端點可達，不可達則拒絕掛載；連接器頁面顯示各連接器健康狀態。遠端 Adapter 共用一份 `execute`，並能列出遠端提供的工具，而非回傳空清單。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 移除匯流排內的 namespace → adapter key 與 namespace → provider 字串對照，改由 Adapter 宣告的 `namespace` / `provider` 決定
- [ ] 取得 OBO 權杖時使用 Adapter 的 `provider`；新增連接器只需在 Adapter 宣告即可接上權杖金庫
- [ ] 掛載遠端工具時呼叫 `health_check()`，失敗回傳清楚錯誤且不寫入工具註冊表
- [ ] 連接器頁面顯示每個連接器的健康狀態（繁體中文），並於瀏覽器驗證
- [ ] Remote MCP 與 HTTP Webhook Adapter 共用 `execute` 實作；`list_tools()` 回傳遠端實際工具
- [ ] 完整測試套件全綠

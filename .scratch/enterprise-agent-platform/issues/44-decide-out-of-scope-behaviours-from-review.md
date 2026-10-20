# 44: 決策：審查標記為超出範圍的行為去留（審查後續：02、07、08、09）

**What to build:** 由人逐項決定以下已實作但不在規格內（或與規格字面不符）的行為要保留、限制或移除，並把決定記錄為 ADR 或規格修訂；需要改程式的項目另開實作 ticket。

1. **`POST /api/v1/users/dev-login`**（02）：目前前端登入與所有測試都依賴它。保留為僅開發環境可用、或改為正式驗證流程？
2. **瀏覽器離線時的行為**（07）：規格寫「優雅回傳 `BROWSER_OFFLINE`」，實作是讓工單休眠為 `WAITING_BROWSER` 等瀏覽器回來。哪一種是預期？
3. **刪除對話的範圍**（08）：規格只要求刪除 Session、Checkpoint 與暫時檔案切片；實作另刪工單、HITL 請求、CLI 紀錄與全部共享產出物。
4. **記憶清理的 `memory_scope` 參數**（08）：規格未定義。
5. **新 Agent 複製 `PM` 的 `output_json_schema`**（08）。
6. **FIN 計算機的 ×0.8／×1.0／×1.2 三情境**與額外 Docker 加固旗標（09）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-human

- [ ] 六項各有明確決定（保留／限制／移除）並寫入 `docs/adr/` 或規格
- [ ] 需要改程式的項目已另開 ticket 並在本 ticket 留言列出編號

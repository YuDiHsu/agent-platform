# 24: 工具匯流排職責拆分與工具呼叫值物件（審查後續：06）

**What to build:** `UnifiedToolBus` 只負責協調：授權（角色授權 ∩ 使用者啟用）、斷路器、Session 短效 `READ` 快取、Adapter 選擇各自成為可單獨測試的部分。工具呼叫以值物件（名稱、參數、層級）在角色執行器與匯流排之間傳遞，取代裸 `(name, args)` tuple。對話中的工具行為、拒絕訊息、逾時、斷路與快取命中都與現在一致。

**Blocked by:** 21: 動作層級型別化與 HITL 整理, 22: 同一回合 READ + DRAFT 平行直通端到端驗收, 23: Adapter 自持 namespace、provider 與健康檢查, 39: CLI 準備流程與執行結果型別整併

**Status:** ready-for-agent

- [ ] 授權判斷、斷路器、快取、Adapter 選擇各自獨立，匯流排只組合它們
- [ ] 工具呼叫值物件取代 `(name, args)` tuple，攜帶型別化的動作層級
- [ ] 斷路器（3 次失敗、30 秒冷卻）、10 秒逾時、60 秒 `READ` 快取、DB session 不跨外部 I/O 等行為不變
- [ ] 06 與 22 的測試不改斷言即全綠；mypy 乾淨

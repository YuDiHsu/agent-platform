# 22: 同一回合 READ + DRAFT 平行直通端到端驗收（審查後續：06）

**What to build:** 補齊 06 的驗收缺口：代理在**同一回合**同時輸出一筆 `READ`（例如信件搜尋）與一筆 `DRAFT`（例如建立草稿）工具呼叫時，兩者都免審批、平行派發，總耗時趨近較慢的一筆而非相加；同回合若另含 `COMMIT`，只有 `COMMIT` 進入 `WAITING_HITL`。目前測試把 `READ` 與 `DRAFT` 放在不同回合，未驗證同回合平行。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 端到端測試：腳本化代理單回合輸出 `READ` + `DRAFT`，兩者皆執行、無審批請求產生
- [ ] 以呼叫時間重疊（或計數＋延遲）證明平行，而非依賴脆弱的總時間門檻
- [ ] 端到端測試：同回合 `READ` + `DRAFT` + `COMMIT`，前兩者完成、`COMMIT` 產生 PENDING 審批並休眠
- [ ] 若測試揭露實作未支援同回合平行，於本 ticket 內修正
- [ ] 完整測試套件全綠（此測試同時作為 24 重構的安全網）

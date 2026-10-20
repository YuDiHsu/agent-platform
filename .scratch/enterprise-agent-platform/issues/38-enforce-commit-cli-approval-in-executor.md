# 38: COMMIT 等級 CLI 技能於執行器層強制審批（審查後續：09）

**What to build:** 不論是誰透過工具匯流排呼叫 `execute_skill_cli`（角色執行器、第 10 張票的背景 Worker 或任何直接呼叫），`COMMIT` 等級的 CLI 技能都必須持有一張對應且已核准的 HITL 審批請求才會執行；否則拒絕並寫入稽核。目前等級閘門只存在角色執行器，CLI adapter 本身不檢查技能等級，其他呼叫者可繞過審批。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] CLI 執行入口在執行前檢查技能等級；`COMMIT` 需有已核准且未使用過的審批請求
- [ ] 無審批或審批不符時拒絕執行、回傳清楚錯誤並寫入 `security_audit_logs`
- [ ] 測試：直接以匯流排呼叫 `COMMIT` CLI 技能被拒；經審批核准後可執行一次；`READ` 技能不受影響
- [ ] 完整測試套件全綠

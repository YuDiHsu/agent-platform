# 16: 規則／技能 API 拆分與技能啟用狀態單一擁有者（審查後續：03）

**What to build:** 使用者在對話中或 Studio 手動啟用技能後，該技能在同一 Session 後續回合都會掛載；「本 Session 已啟用哪些技能」只有一個擁有者負責讀寫 checkpoint，手動啟用路由與角色執行器都透過它。規則、技能、Prompt 預覽各自成為獨立的 API 模組，不再因不相關的理由改同一支檔案。`skill_activated` 事件只由對話串流發出一次。

**Blocked by:** 15: 隱藏資產守門與審核狀態型別化

**Status:** ready-for-agent

- [ ] 規則、技能、Prompt 預覽拆成獨立的 API 模組，路由路徑與回應不變
- [ ] Session checkpoint 中 `activated_skills` 的讀取與寫入集中於單一模組；手動啟用路由與角色執行器不再各寫一份
- [ ] 手動啟用路由不再自行產生 `skill_activated` SSE；事件只由 Supervisor 對話串流發出，前端仍正確顯示「已啟用技能」
- [ ] 測試覆蓋：手動啟用後下一回合 Layer 6 掛載該技能 SOP；同技能重複啟用不重複寫入
- [ ] 完整測試套件全綠，並於瀏覽器確認 Studio 技能啟用流程

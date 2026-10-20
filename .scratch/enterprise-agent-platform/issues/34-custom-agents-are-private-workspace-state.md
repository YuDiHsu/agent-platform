# 34: 自建 Agent 成為私有工作區狀態（審查後續：08）

**What to build:** User A 建立、修改、停用或刪除自己的自建 Agent，只影響 A 的工作區；User B 可以用相同的代碼建立自己的 Agent 而不衝突。目前 `agent_roles.code` 全域唯一，刪除會把共用列設為 `is_active=false`，修改會改共用的 `name` 與 `system_prompt`。建立時若遇到代碼衝突，回應清楚的「代碼已存在」，而非誤報 `ERR_LOCAL_MOUNT_MUST_BE_PRIVATE`。

**Blocked by:** 33: 個人工作區名單整併

**Status:** ready-for-agent

- [ ] 自建 Agent 的代碼唯一性以擁有者為範圍（公開上架後的唯一性規則一併明確化）
- [ ] 修改、停用、刪除自建 Agent 只作用於擁有者
- [ ] 代碼衝突回 409 與繁中訊息；`ERR_LOCAL_MOUNT_MUST_BE_PRIVATE` 只在本機掛載對外發布時出現
- [ ] 測試：A 與 B 同代碼各自建立；A 修改／刪除後 B 不受影響；兩種錯誤碼分別觸發
- [ ] 資料庫遷移可升級與降級

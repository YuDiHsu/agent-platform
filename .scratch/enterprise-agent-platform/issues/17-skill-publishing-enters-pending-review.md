# 17: 技能發布進入 PENDING_REVIEW 審核（審查後續：03）

**What to build:** 一般使用者在 Studio 建立技能並選擇分享到部門或全域時，技能進入 `PENDING_REVIEW`；在 Admin 核准前，其他使用者的目錄與 Layer 6 都看不到它，建立者在 Studio 看得到「審核中」狀態。Admin 建立或僅限私人／角色專屬的技能則直接 `APPROVED`。目前所有新技能一律為 `PRIVATE` + `APPROVED`，從未進入審核。

**Blocked by:** 16: 規則／技能 API 拆分與技能啟用狀態單一擁有者

**Status:** ready-for-agent

- [ ] 建立技能可指定分享範圍；審核狀態規則與規則（Rules）建立一致：Admin 或非公開範圍為 `APPROVED`，一般使用者對外分享為 `PENDING_REVIEW`
- [ ] `PENDING_REVIEW` 技能不出現在他人目錄、Stage-1 manifest 與 Layer 6；建立者自己可見並標示「審核中」
- [ ] Admin 核准後技能對目標範圍可見並可被檢索掛載
- [ ] 測試覆蓋上述三種情境（Admin 直接核准、一般使用者送審不可見、核准後可見）
- [ ] 瀏覽器驗證 Studio 顯示審核狀態

# 29: 所有 Modal／抽屜的 Focus Trap 與 Esc 關閉（審查後續：02）

**What to build:** 使用者只用鍵盤時，開啟任何 Modal 或抽屜（導覽抽屜、工作台抽屜、HITL 通知抽屜、組織圖角色抽屜、Studio 精靈等）後焦點會被限制在其中，按 `Esc` 即關閉並把焦點還給開啟它的按鈕。目前 Esc 只關導覽與工作台，組織圖角色抽屜與 HITL 抽屜不會關，且沒有任何 Focus Trap。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 共用一個抽屜／Modal 行為（Focus Trap、Esc 關閉、關閉後焦點還原），所有抽屜與 Modal 使用它
- [ ] 組織圖角色抽屜與 HITL 通知抽屜支援 Esc 關閉
- [ ] Tab／Shift+Tab 在開啟的抽屜內循環，不會跑到背景
- [ ] 瀏覽器以純鍵盤驗證每一個抽屜與 Modal

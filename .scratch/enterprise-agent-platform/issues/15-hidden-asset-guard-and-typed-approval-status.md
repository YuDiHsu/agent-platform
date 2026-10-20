# 15: 隱藏資產守門與審核狀態型別化（審查後續：03、04）

**What to build:** 一般使用者對規則、技能、工具任何一種底層隱藏資產（`is_visible_to_user = false`）的關閉、修改或讀取，都經過同一個守門判斷並得到一致的 403/404。「是否可見」與「審核狀態」作為一個值一起傳遞；審核狀態與洋蔥層級不再是裸字串。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 規則、技能、工具 API 共用同一個隱藏資產守門（含錯誤訊息「底層資產不可關閉」），移除各自重複的常數與判斷
- [ ] `is_visible_to_user` 與 `approval_status` 以單一值物件表達資產對某使用者的可見性，目錄過濾與 Layer 組裝共用
- [ ] `approval_status`（`APPROVED` / `PENDING_REVIEW` …）與 Prompt 層級（Layer 1–6）改為列舉型別，mypy 能攔截拼錯的值
- [ ] 洋蔥編譯器中意圖不清的「啟用列」過濾函式改為清楚的名稱
- [ ] Prompt 預覽重用 `PromptSegment` 的渲染，不再自行重組字串
- [ ] 既有 403/404、目錄可見性與 Prompt 預覽輸出行為不變；完整測試套件全綠

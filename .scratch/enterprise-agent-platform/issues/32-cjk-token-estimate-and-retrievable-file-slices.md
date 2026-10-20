# 32: 大型文件 Token 估算正確與暫時檔案切片可被檢索（審查後續：07）

**What to build:** 使用者讓代理讀取一份超過 3,000 tokens 的本機 `.docx`／`.xlsx`／`.pdf`（含純繁體中文文件）時，文件會被切片寫入 `EPHEMERAL_LOCAL_FILE`；之後在同一對話追問文件細節，相關切片會被檢索並放進 Prompt。目前門檻是「3000 × 4 個字元」，中文文件常常不會被切片；切片寫入後也沒有任何地方讀取它。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 切片門檻使用與 Stage-1 manifest 一致的 Token 估算（CJK 字元以較高權重計），而非固定字元倍數
- [ ] 記憶檢索在同一 Session 內納入 `EPHEMERAL_LOCAL_FILE` 切片（僅限擁有者本人、本 Session）
- [ ] 測試：約 2,000 個中文字的文件會被切片；追問時 Prompt 含相關切片；他人或他 Session 看不到
- [ ] 完整測試套件全綠

# 30: 本機掛載資料形狀與敏感路徑政策單一來源（審查後續：07）

**What to build:** 本機掛載在 bootstrap、工具參數、反向 RPC 與瀏覽器端都使用同一組欄位名稱（例如只用一種 path 與 handle key），不再兩套並存、到處 `a or b` 相容。敏感路徑黑名單（`.env`、`.pem`、`.pfx`、`id_rsa`、`.git/`、`node_modules/`、`..`）只有一個來源，後端與瀏覽器使用同一份。使用者的掛載、讀寫、拒絕與稽核行為不變。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Bootstrap 只回傳一種掛載投影；前後端移除雙欄位相容判斷
- [ ] 敏感路徑政策由後端單一定義，瀏覽器端取得同一份（例如經 bootstrap 下發），不再手抄
- [ ] `BROWSER_OFFLINE` 回應只定義一次；反向 RPC 的「配發 id → 等待 → 逾時」只有一份實作
- [ ] 角色執行器的瀏覽器分支重用既有的結果摘要與結構化生成流程；離線判斷改讀匯流排已提供的錯誤
- [ ] 瀏覽器端確認寫入的重複 try/catch 合併；`grantedWrite` 改為表達「本次審批已核准、可略過 diff」的名稱；移除未被讀取的欄位
- [ ] 07 的測試不改斷言即全綠；tsc 乾淨

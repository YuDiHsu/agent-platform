# 27: Token 計量、額度暫停與組織圖角色即時狀態（審查後續：02）

**What to build:** 每次模型呼叫的 Token 用量累加到該工單的 `tokens_consumed` 與使用者的 `tokens_consumed_total`；新使用者有預設額度。用量超過額度時，進行中的工作進入 `PAUSED_QUOTA_EXCEEDED` 休眠，額度提高後可於原對話續跑。組織圖的 Token 進度條會真的移動，角色節點顯示的是「目前進行中」的工單狀態，而不是最新建立的工單。

**Blocked by:** 25: DAG 快照型別化與工作區還原整併

**Status:** ready-for-agent

- [ ] 主代理與子代理每次模型呼叫後寫入工單 `tokens_consumed` 與使用者 `tokens_consumed_total`
- [ ] 新使用者具預設 `token_quota_limit`（可設定）
- [ ] 用量超過額度時休眠為 `PAUSED_QUOTA_EXCEEDED`，不佔連線；額度提高後於原對話續傳
- [ ] 組織圖角色節點顯示進行中工單的狀態；沒有進行中工單時才顯示最近一筆
- [ ] 測試覆蓋計量累加、超額暫停與續傳；瀏覽器驗證組織圖進度條

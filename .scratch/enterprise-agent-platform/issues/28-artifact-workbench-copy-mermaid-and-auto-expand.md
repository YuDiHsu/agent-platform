# 28: 產出物工作台補齊：複製按鈕、~~~mermaid 偵測與窄螢幕自動展開（審查後續：02）

**What to build:** 使用者在產出物工作台看到的程式碼區塊有「複製」按鈕；以 `~~~mermaid` 或 ```` ```mermaid ```` 包住的圖都會渲染成可縮放平移的 SVG。窄螢幕下收到 `orchestrator_plan` 或 `artifact_created` 時，底部工作台抽屜自動展開到對應分頁，而不是只切換分頁但抽屜仍關著。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 每個程式碼區塊有可鍵盤操作的「複製」按鈕，複製後以 `aria-live` 宣告「已複製」
- [ ] `~~~mermaid` 與 ```` ```mermaid ```` 兩種圍欄都渲染為可縮放平移的 Mermaid 圖
- [ ] 窄螢幕下 `artifact_created` 自動展開工作台並切到 `ARTIFACT` 分頁；`orchestrator_plan` 展開到 DAG 分頁
- [ ] 瀏覽器驗證寬窄兩種視窗

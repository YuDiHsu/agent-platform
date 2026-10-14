# 07: 跨 Worker Redis Pub/Sub 瀏覽器本機反向 RPC 橋接、記憶體文件解析與紅綠 Diff 寫入

**What to build:** 讓使用者無須安裝桌面程式即可在 Chrome 或 Edge 透過 W3C File System Access API 授權本機工作資料夾（Handle 持久化於 IndexedDB），並將後端 `WebSocketReverseRPCManager` 升級為基於 **Redis Pub/Sub 的跨 Worker 路由背板**，確保在多人同時在線、啟動多個 FastAPI/Uvicorn Workers 與獨立 Celery Workers 時，任何 Worker 發起的 `CLIENT_FS_READ` / `CLIENT_FS_WRITE` 都能精準路由至持有該使用者 WebSocket 連線的 Worker。使用者登出再登入時，前端根據 Bootstrap 資料自動匹配 IndexedDB Handle 無感重連。讀取 `.docx`、`.xlsx`、`.pdf` 時於記憶體經 `MarkItDown` 轉為 Markdown（超過 3,000 tokens 自動切片存入暫時向量記憶）；寫入本機檔案前強制觸發右側工作區 `FILE_DIFF` 紅綠並排比對，經使用者確認後才寫入硬碟。

**Blocked by:** 02: 多代理 DAG 任務編排、Claim-Check 產出物指標、跨登入工作階段持久化與斷點休眠工作區, 05: HITL 人工審批安全閘門（READ / DRAFT / COMMIT）與狀態機斷點續傳

**Status:** ready-for-agent

- [ ] 前端支援呼叫瀏覽器原生目錄選擇器授權本機資料夾、持久化 Handle 至 IndexedDB，並在重新登入時根據 Bootstrap 回傳的 `local_workspace_mounts` 自動檢驗權限與恢復連線（若瀏覽器重啟需重授則提供一鍵恢復按鈕，無須重新選資料夾）；在行動端或不支援的瀏覽器上提供清楚替代指引（`REQ-004`, `ADR-001`, `ADR-0002`, `PRODUCT.md`）
- [ ] 後端 `WebSocketReverseRPCManager` 結合本機連線池與 Redis Pub/Sub 跨 프로세스背板：支援從任一 API Worker 或 Celery Worker 發起反向 RPC 並回收 `asyncio.Future` 結果，具備 30 秒逾時斷路器，且在等待瀏覽器回應期間先釋放 DB Session；當瀏覽器離線時優雅回傳 `BROWSER_OFFLINE`（`REQ-004`, `ADR-0002`）
- [ ] 嚴格阻擋跨使用者存取：當請求者 `user_id` 與掛載擁有者不一致時，立即記錄資安稽核事件並拋出 `ERR_LOCAL_MOUNT_MUST_BE_PRIVATE` 權限錯誤（`REQ-012`）
- [ ] 前後端雙重攔截路徑穿越（`..`）與敏感檔案規則（`.env`, `.pem`, `.pfx`, `id_rsa`, `.git/`, `node_modules/`），任何讀取或寫入嘗試均被拒絕並寫入資安稽核表（`REQ-012`, `TC-M3-03`, `ADR-0004`）
- [ ] 讀取 `.docx`、`.xlsx`、`.pdf` 時於記憶體無狀態轉換為 Markdown；超過 3,000 tokens 的文件自動切片寫入 `EPHEMERAL_LOCAL_FILE` 記憶區供檢索（`REQ-004`, `TC-M3-02`）
- [ ] 呼叫 `workspace_write_file` 時強制觸發 HITL 暫停，前端自動展開右側 `FILE_DIFF` 分頁呈現左右紅綠 Diff 比對，僅在使用者點擊「確認寫入本機硬碟」後才透過瀏覽器寫入磁碟（`REQ-004`, `REQ-007`, `REQ-010`, `TC-M3-02`, `UI_SPEC.md`）

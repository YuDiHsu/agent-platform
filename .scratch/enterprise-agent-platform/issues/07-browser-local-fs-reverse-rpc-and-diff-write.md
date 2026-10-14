# 07: 瀏覽器本機資料夾反向 RPC 橋接、記憶體文件解析與紅綠 Diff 寫入確認

**What to build:** 讓使用者無須安裝任何桌面程式，即可在 Chrome 或 Edge 瀏覽器透過 W3C File System Access API 授權本機工作資料夾（Handle 持久化於 IndexedDB），並透過雙向 WebSocket JSON-RPC 2.0 反向通道（Reverse RPC）供後端角色代理安全讀寫本機檔案。讀取 `.docx`、`.xlsx`、`.pdf` 等二進位辦公室文件時，後端在記憶體內透過 `MarkItDown` 無狀態轉為結構化 Markdown（若超過 3,000 tokens 則自動切片存入具時效性的暫時向量記憶）；當代理請求修改或新增本機檔案時，系統強制攔截並於前端彈出紅綠 Diff 比對預覽視窗，必須由使用者點擊「核准並寫入本機」後，瀏覽器才實際寫入硬碟。前後端雙重強制阻擋路徑穿越與敏感憑證檔案。

**Blocked by:** 02: 多代理 DAG 任務編排、Claim-Check 產出物指標與即時串流對話工作區, 05: HITL 人工審批安全閘門（READ / DRAFT / COMMIT）與狀態機斷點續傳

**Status:** ready-for-agent

- [ ] 前端支援呼叫瀏覽器原生目錄選擇器授權本機資料夾，將 `FileSystemDirectoryHandle` 存入 IndexedDB，並過濾黑名單後同步相對路徑檔案樹至後端註冊；在行動裝置或不支援 File System Access API 的瀏覽器上，提供清楚的環境限制提示與雲端連接器／`Local MCP Daemon` 替代指引（`REQ-004`, `ADR-001`, `PRODUCT.md`）
- [ ] 後端反向 RPC 管理器維護 `(user_id, session_id)` 連線池與 30 秒逾時斷路器；當瀏覽器未連線時優雅回傳 `BROWSER_OFFLINE` 狀態而不崩潰（`REQ-004`）
- [ ] 嚴格阻擋跨使用者存取：當請求者 `user_id` 與掛載擁有者不一致時，立即拋出 `ERR_LOCAL_MOUNT_MUST_BE_PRIVATE` 權限錯誤（`REQ-012`）
- [ ] 前後端雙重攔截路徑穿越（`..`）與敏感檔案規則（`.env`, `.pem`, `.pfx`, `id_rsa`, `.git/`, `node_modules/`），任何讀取或寫入嘗試均被拒絕（`REQ-012`, `TC-M3-03`）
- [ ] 讀取 `.docx`、`.xlsx`、`.pdf` 時於記憶體無狀態轉換為 Markdown；超過 3,000 tokens 的文件自動切片寫入 `EPHEMERAL_LOCAL_FILE` 記憶區供檢索（`REQ-004`, `TC-M3-02`）
- [ ] 呼叫 `workspace_write_file` 時強制觸發 HITL 暫停，前端全域狀態機自動展開右側工作區並切換至 `FILE_DIFF` 分頁，以左右並排紅綠 Diff 比對原始內容與預計寫入內容，僅在使用者點擊「確認寫入本機硬碟」後才透過瀏覽器寫入磁碟；此外右側 `ARTIFACT` 分頁亦支援將產出物直接寫入本機掛載資料夾（`REQ-004`, `REQ-007`, `REQ-010`, `TC-M3-02`, `UI_SPEC.md`）

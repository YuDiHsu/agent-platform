# 09: 雙目標參數化防注入 CLI 執行器、併發限流 Rootless Docker 沙盒與即時 ANSI 終端機卡片

**What to build:** 實作支援雙執行目標（伺服器端無根容器沙盒 `SERVER_SANDBOX_CLI` 與工程師本機守護進程 `LOCAL_DAEMON_CLI`）的參數化技能 CLI 執行引擎，以及前端即時 ANSI 終端機輸出卡片。所有 CLI 技能嚴禁拼接任意原始 Shell 字串，必須定義含 `{{param}}` 佔位符的指令範本，執行前先通過嚴格的 JSON Schema 參數驗證（拒絕未宣告的額外屬性）、將每個參數以 `shlex.quote()` 安全跳脫，並檢查危險指令黑名單。為確保多人同時在線時不因大量啟動容器耗盡主機資源，`SERVER_SANDBOX_CLI` 採用 Semaphore 併發閘門控制同時執行的無網路、唯讀根目錄 Rootless Docker 容器數量，自動從瀏覽器掛載同步目標檔案，將執行與攔截紀錄寫入稽核表，並透過 SSE 將指令、目標徽章、Exit Code 與 stdout/stderr 串流至前端終端機卡片呈現。

**Blocked by:** 03: 洋蔥式規範隔離編譯器、兩階段漸進式技能與系統底層隱藏資產（is_visible_to_user=false）, 05: HITL 人工審批安全閘門（READ / DRAFT / COMMIT）與狀態機斷點續傳, 07: 跨 Worker Redis Pub/Sub 瀏覽器本機反向 RPC 橋接、記憶體文件解析與紅綠 Diff 寫入

**Status:** ready-for-agent

- [ ] 參數化指令渲染器強制執行 JSON Schema 驗證（`additionalProperties: false`）、`shlex.quote` 參數跳脫、未替換佔位符檢查與 `FORBIDDEN_CLI_TOKENS` 黑名單攔截；任何指令注入嘗試（如 `; rm -rf /`）均被安全阻擋並記錄至資安稽核表（`REQ-016`, `ADR-004`, `TC-M5-04`, `ADR-0004`）
- [ ] 伺服器端 Docker 沙盒執行器以無網路（`network_mode="none"`）、記憶體上限 `512m`、`pids_limit=64`、唯讀根目錄（`read_only=True`）與暫時性 `/workspace` 啟動容器，執行完畢或逾時即自動銷毀容器，並透過非同步 Semaphore 限制全系統同時執行之容器上限以保護多人併發穩定度（`REQ-015`, `ADR-0002`）
- [ ] 支援自動檔案同步：當 `SERVER_SANDBOX_CLI` 技能設定 `sync_local_files` 時，自動透過跨 Worker 瀏覽器反向 RPC 讀取目標本機檔案並注入沙盒工作區（`REQ-015`, `TC-M5-03`）
- [ ] 內建並驗證兩支沙盒技能腳本：`SKILL_SA_OPENAPI_CLI_VALIDATOR`（OpenAPI 規格驗證）與 `SKILL_FIN_PYTHON_IRR_CALCULATOR`（精準計算 NPV/IRR/回收期與三情境表格）（`TC-M5-03`）
- [ ] `READ` 等級 CLI 技能驗證通過後自動執行；`COMMIT` 等級 CLI 技能強制暫停於 `WAITING_HITL` 並預覽完整渲染後指令供使用者審批（`REQ-007`, `REQ-016`, `TC-M5-04`）
- [ ] 每次 CLI 執行均寫入 `cli_execution_logs` 稽核表並推播 `cli_output` SSE 事件；前端全域狀態機收到事件後自動展開右側工作區並切換至 `TERMINAL_CLI` 暗色終端機分頁，顯示執行目標徽章、安全跳脫後的指令、耗時（`ms`）、`exit_code` 與 `stdout` / `stderr`（`REQ-010`, `REQ-015`, `UI_SPEC.md`）

# 0003: 個人獨立工作區與 Agent 環境隔離、背景斷點休眠與預設範本重置機制

Status: accepted

雖然所有使用者共用同一套機房 SGLang 推論叢集與應用程式伺服器，但每位使用者的工作區與 Agent 環境必須完全獨立且互不干擾，同時兼顧關閉瀏覽器後的背景續跑與低伺服器負載：

1. **個人獨立 Agent 環境與自由增刪開關**：`seed_roles.yaml` 定義的是「系統預設角色範本（Default Preset Templates）」。每位使用者擁有各自獨立的 Agent 工作區狀態，可自由新增、修改、開啟（`is_enabled=true`）、關閉（`is_enabled=false`）或刪除任何 Agent（包含預設的 7 個角色），絕不影響其他使用者的環境；並隨時可透過 UI 按鈕或 `POST /api/v1/agents/presets/reset` 指令從系統預設範本一鍵還原單一或全部預設 Agent。
2. **斷線續跑、零待機休眠（Checkpoint Hibernation）與事件持久化**：對話與 DAG 執行與瀏覽器 HTTP 連線脫鉤，每筆訊息與角色狀態變更皆寫入 `chat_messages`。當工單進入 `WAITING_HITL` 或等待離線瀏覽器掛載時，狀態存妥於 PostgreSQL Checkpoint 後 Worker 立即釋放任務（佔用 0% CPU 與 0 MB RAM），待使用者隔天登入或點擊審批時再行喚醒；並透過每人同時執行中工單配額與重度 I/O 專用佇列防止單一使用者阻塞伺服器。
3. **三層記憶清理粒度**：在 `agent_memories` 記錄選填之 `role_code`，支援使用者按「單一角色」、「單一對話工作階段」或「全部個人私有／本機暫時記憶」進行清理。

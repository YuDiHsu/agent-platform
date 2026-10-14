# 0002: 可插拔 Tool Adapter 三層交集模型與多人高併發執行架構

Status: accepted

為支援後端人員彈性擴充新工具、讓使用者自主選擇是否啟用工具，並確保數十至數百名使用者同時在線時不發生推論延遲或連線池耗盡，我們做下四項架構決策：

1. **Tool Adapter 雙軌統一接口與三層啟用交集**：在 `UnifiedToolBus` 定義 `BaseToolAdapter` 介面，同時支援「Python `@register_tool_adapter` 程式碼模組註冊」與「資料庫動態註冊遠端 MCP Server / HTTP Webhook」。新增 `tools_registry`（區分全角色共通預設 `COMMON_DEFAULT` 與角色限定 `ROLE_SCOPED`）、`agent_role_tools` 與 `user_tool_preferences`；單一回合實際可用工具嚴格取「角色授權工具 $\cap$ 使用者個人啟用工具」之交集。
2. **Tool Calling 低延遲與 KV Cache 保護**：動態篩選後的 Top-5 工具 Schema 一律注入於洋蔥式提示詞最外層尾端（Layer 6 / 回合上下文），保持 Layer 1~4 靜態前綴 100% 跨使用者共享 SGLang RadixAttention 快取；同一回合的多筆 `READ` / `DRAFT` 工具呼叫由 `asyncio.gather()` 平行派發，每個 Adapter 強制配置獨立 Timeout（預設 10s）、斷路器與可選的 Redis 讀取短效快取。
3. **跨 Worker WebSocket 背板與無長佔 DB 交易**：`WebSocketReverseRPCManager` 透過 Redis Pub/Sub 跨 FastAPI/Uvicorn Workers 與 Celery Workers 路由瀏覽器與本機 Daemon 的反向 RPC；在等待 LLM 推論、外部 MCP HTTP 或瀏覽器 RPC 的所有 I/O 期間，強制先釋放 SQLAlchemy `AsyncSession`，並共用全域 `httpx.AsyncClient` 連線池與 Docker 沙盒 Semaphore 併發閘門。
4. **使用者設定與工作階段跨登入持久化**：透過 `chat_sessions`、`user_tool_preferences` 與 `GET /api/v1/users/me/bootstrap` 端點，確保使用者登出再登入或重開瀏覽器時，自動還原所有自建代理、工具開關、歷史對話與本機掛載狀態。

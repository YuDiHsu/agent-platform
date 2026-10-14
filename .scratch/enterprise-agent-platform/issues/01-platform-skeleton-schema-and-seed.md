# 01: 平台最小可行骨架、13 表資料庫遷移與內建角色/規範/技能種子載入

**What to build:** 建立可啟動並通過健康檢查與種子驗證的企業多代理協作平台最小可行骨架（Walking Skeleton）。啟動容器化基礎設施（PostgreSQL 16 含 `pgvector` 與 Redis 7）、後端 API 服務與前端 Web 入口殼層；完成涵蓋使用者、本機掛載、角色、規範、技能、產出物、工單、HITL 審批、CLI 紀錄、加密權杖與三層向量記憶的 13 張關聯式與向量資料表結構遷移；提供本地 Gemma 4 結構化 JSON Schema 推論與可配置之 OpenAI 相容向量嵌入能力（依 `ADR-0001` 透過環境變數設定 `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL_NAME` 如 `BAAI/bge-m3` 與 `EMBEDDING_DIMENSION`），並支援以冪等（Idempotent）方式載入 7 個內建企業角色（`ORCH`, `CEO`, `PM`, `FIN`, `SA`, `ARCH`, `SE`）、5 條核心規範與 4 項內建技能及其向量嵌入。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] 容器編排設定與環境變數範本可正常解析並啟動 PostgreSQL 16（啟用 `uuid-ossp` 與 `vector` 擴充套件）及 Redis 7 服務（對應 `REQ-001`, `REQ-008`, `REQ-012`）
- [x] 資料庫遷移可從零建立全部 13 張核心資料表、外鍵約束、`chk_local_mount_private` 私有範圍檢查約束，以及角色路由、技能觸發與代理記憶三座 HNSW 餘弦相似度向量索引（向量欄位維度依 `ADR-0001` 讀取 `settings.EMBEDDING_DIMENSION`，不寫死常數）
- [x] 結構化推論客戶端強制附加 JSON Schema 約束解碼（Strict Mode），於連續 50 次推論測試中達成 100% 合法 Pydantic 模型解析率（`TC-M1-03`）
- [x] 向量嵌入客戶端（依 `ADR-0001` 採用可配置之 OpenAI 相容 `/v1/embeddings` 介面，預設支援 `BAAI/bge-m3` 等模型）支援單筆與批次文字轉 `EMBEDDING_DIMENSION` 維正規化浮點數向量
- [x] 內建種子載入器可重複執行而不產生重複紀錄（Idempotent），完整寫入 7 個內建角色、5 條核心規範（2 條全公司強制、3 條角色專屬）、4 項內建技能及其 M:N 綁定關係與對應維度之向量嵌入（`TC-M1-01`, `ADR-0001`）

## Comments

- 2026-10-14: 骨架已落地。`docker-compose.yml` 與 `.env.example` 可解析；遷移依 `settings.EMBEDDING_DIMENSION` 建立 13 表與三座 HNSW 索引。本機沒有 Docker，資料庫行為以 PGlite（pgvector）驗證。PGlite 映像未內建 `uuid-ossp` 時，遷移改以核心 `gen_random_uuid()` 提供同名 `uuid_generate_v4()`；`pgvector/pgvector:pg16` 仍會建立 `uuid-ossp`。

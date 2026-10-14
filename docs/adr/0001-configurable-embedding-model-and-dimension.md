# 0001: 可配置之 OpenAI 相容 Embedding 模型與動態向量維度

Status: accepted

雖然唯讀的 `MASTER_SPEC.md` 原始記載使用 `google/embeddinggemma-2` 與固定 `VECTOR(768)`，但實際機房部署尚未鎖定單一 Embedding 模型（優先考慮 `BAAI/bge-m3` 1024 維或其他繁體中文／多語系開源模型，且不採用 `embeddinggemma-2`）。為避免日後更換模型或調整向量維度時需要修改多處程式碼與資料庫模型，我們決定將 Embedding 模組設計為由環境變數驅動的深度模組（Deep Module）：透過 `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL_NAME`（如 `BAAI/bge-m3`）與 `EMBEDDING_DIMENSION`（如 `1024` 或 `768`）統一走 OpenAI 相容 `/v1/embeddings` 介面，並在 SQLAlchemy 模型（`agent_roles.routing_embedding`、`skills_registry.trigger_embedding`、`agent_memories.embedding`）與 Alembic 遷移中直接讀取 `settings.EMBEDDING_DIMENSION`。

## Consequences

- 覆蓋 `MASTER_SPEC.md` 中寫死 `google/embeddinggemma-2` 與 `768` 維常數的假設；所有驗收測試（如 `TC-M1-01`）改為驗證向量維度等於 `settings.EMBEDDING_DIMENSION`。
- 當機房確定最終模型（例如 `BAAI/bge-m3` 1024 維或 `BAAI/bge-base-zh-v1.5` 768 維）時，僅需調整 `.env` 並重新執行資料庫遷移與冪等種子載入器（`seed_runner.py`），無須修改業務邏輯程式碼。

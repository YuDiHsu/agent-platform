# 04: 個人 OBO 權杖加密金庫、可插拔 tools_registry 三層偏好開關與動態 Tool RAG

**What to build:** 建立企業零信任身分驗證、個人外部連接器權杖加密金庫（AES-256-GCM Token Vault）、可插拔工具註冊表（`tools_registry`）與三層工具啟用交集模型（共通預設 `COMMON_DEFAULT` / 角色綁定 `agent_role_tools` / 使用者個人開關 `user_tool_preferences`），以及基於 `pgvector` HNSW 的動態角色與工具檢索器（Dynamic Role & Tool RAG）。每位使用者可在前端自由選擇要啟用或停用哪些 Tools / Connectors（設定持久化於資料庫，登出再登入自動還原）；編排器在每回合對話僅從「角色有權限 $\cap$ 使用者已勾選啟用（外加 `is_visible_to_user = false` 之系統底層強制工具）」的交集池中，依向量餘弦相似度檢索 Top-5 工具注入推論。

**Blocked by:** 01: 平台最小可行骨架、13 表資料庫遷移與內建角色/規範/技能種子載入

**Status:** ready-for-agent

- [x] 權杖金庫採用 AES-256-GCM 與每筆紀錄獨立隨機 Nonce 加解密存取權杖與重新整理權杖，密文遭竄改時拋出驗證失敗例外，且僅允許權杖擁有者本人的執行上下文解密取用（`REQ-006`, `REQ-012`）
- [x] 建立 `tools_registry`（含 `code`, `namespace`, `input_json_schema`, `action_tier`, `scope_type` (`COMMON_DEFAULT` | `ROLE_SCOPED`), `is_visible_to_user`, `timeout_seconds`, `routing_embedding`）、`agent_role_tools`（角色工具 M:N 綁定）與 `user_tool_preferences`（使用者個人工具啟停開關）（`ADR-0002`, `ADR-0004`）
- [x] 提供工具目錄與個人工具開關 API（`GET /api/v1/tools`, `PUT /api/v1/users/me/tool-preferences`）及前端連接器與工具開關設定頁面；當使用者關閉某項工具時，狀態永久保存，登出再登入仍維持該設定（`ADR-0002`）
- [x] 動態檢索器使用 `pgvector` 餘弦距離（`<=>`）檢索候選角色與可用工具，嚴格過濾 `visibility_scope` 與三層工具交集（僅回傳角色被授權且使用者設為 `is_enabled = true` 的工具，外加 `is_visible_to_user = false` 的底層強制工具）（`REQ-009`, `REQ-012`, `ADR-0002`, `ADR-0004`）
- [x] 單一角色每回合動態注入之工具數量硬性上限為 Top-5（`TC-M2-03`）

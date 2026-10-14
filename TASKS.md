# Enterprise Multi-Agent Platform - Execution Task Tracker (`TASKS.md`)

- **Blueprint Reference**: `MASTER_SPEC.md` (`EAMP-MASTER-SPEC-2026-V3.0` - **READ ONLY**)
- **Target Model**: `gemini-4-argon`
- **Agent Execution Protocol**:
  1. Always read `MASTER_SPEC.md` first for schemas, code contracts, and architecture rules (**DO NOT modify `MASTER_SPEC.md`**).
  2. Pick the next uncompleted task (`- [ ]`) in sequential order (`TASK-01` -> `TASK-28`).
  3. Check the task's **`[THINKING: MEDIUM]`** or **`[THINKING: HIGH]`** badge before generating code.
  4. Implement the exact **Target Files** listed for that task without any `# TODO` or placeholder stubs.
  5. Run the **Verification Command**. Only after it exits with code `0`, update `- [ ]` to `- [x]` in this `TASKS.md` file and record the completion timestamp.

---

## Progress Summary

| Milestone | Scope | Total Tasks | Thinking Profile | Status |
| :--- | :--- | :---: | :--- | :--- |
| **Milestone 1** | Core Infra, 13-Table DB, SGLang Client & LangGraph DAG | 7 (`TASK-01` ~ `TASK-07`) | 5 `MEDIUM` / 2 `HIGH` | `[ ] Pending` |
| **Milestone 2** | Token Vault, HITL Interceptor, Enterprise MCPs & Tool RAG | 6 (`TASK-08` ~ `TASK-13`) | 4 `MEDIUM` / 2 `HIGH` | `[ ] Pending` |
| **Milestone 3** | Browser Local FS Reverse RPC, Doc Parser & Next.js Studio | 6 (`TASK-14` ~ `TASK-19`) | 4 `MEDIUM` / 2 `HIGH` | `[ ] Pending` |
| **Milestone 4** | 24/7 Celery Heartbeats, Local MCP Daemon & Zero-Trust Audit | 4 (`TASK-20` ~ `TASK-23`) | 3 `MEDIUM` / 1 `HIGH` | `[ ] Pending` |
| **Milestone 5** | Onion Rule/Skill Compiler, Parameterized CLI & Docker Sandbox | 5 (`TASK-24` ~ `TASK-28`) | 3 `MEDIUM` / 2 `HIGH` | `[ ] Pending` |

---

## Milestone 1: Foundation, 13-Table DB Schema & Gemma 4 DAG Orchestrator

- [ ] **TASK-01** `[THINKING: MEDIUM]` — **Scaffold Monorepo, Docker Compose & Backend Dependencies**
  - **Implements**: `REQ-001`, `REQ-008`, `REQ-012`
  - **Target Files**:
    - `docker-compose.yml` (PostgreSQL 16 with `pgvector/pgvector:pg16`, Redis 7, API, Worker, Web)
    - `.env.example`
    - `apps/api-server/pyproject.toml` (FastAPI, SQLAlchemy 2.0, asyncpg, pgvector, alembic, langgraph, langgraph-checkpoint-postgres, openai, pydantic v2, celery, redis, markitdown, docker, jsonschema, pyyaml, pytest)
    - `apps/api-server/app/core/config.py`
  - **Verification Command**: `docker compose config -q && cd apps/api-server && pip install -e .`

- [ ] **TASK-02** `[THINKING: MEDIUM]` — **Implement All 13 SQLAlchemy 2.0 Models & Alembic Initial Migration**
  - **Implements**: `REQ-001` ~ `REQ-016` (Section 5 of `MASTER_SPEC.md`)
  - **Target Files**:
    - `apps/api-server/app/db/session.py`
    - `apps/api-server/app/db/models.py` (Exact 13 tables in FK-safe order, including `chk_local_mount_private` constraint and HNSW vector indexes)
    - `apps/api-server/alembic.ini`
    - `apps/api-server/alembic/env.py`
    - `apps/api-server/alembic/versions/0001_unified_schema.py`
  - **Verification Command**: `cd apps/api-server && alembic upgrade head`

- [ ] **TASK-03** `[THINKING: MEDIUM]` — **Implement SGLang Gemma 4 Guided-JSON Client & EmbeddingGemma-2 Client**
  - **Implements**: `REQ-008`, `REQ-009` (Section 6.1 of `MASTER_SPEC.md`)
  - **Target Files**:
    - `apps/api-server/app/llm/gemma_client.py` (`GemmaSGLangClient.generate_structured` with `json_schema` strict mode)
    - `apps/api-server/app/llm/embedding_client.py` (`EmbeddingGemmaClient.embed_text` & `embed_batch` returning 768-d vectors)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_llm_clients.py -v`

- [ ] **TASK-04** `[THINKING: MEDIUM]` — **Create Built-in Seed YAML Files & Idempotent Database Seeder**
  - **Implements**: `REQ-001`, `REQ-013`, `REQ-014` (Section 7 of `MASTER_SPEC.md`)
  - **Target Files**:
    - `packages/builtin-roles/seed_roles.yaml` (7 core roles: `ORCH`, `CEO`, `PM`, `FIN`, `SA`, `ARCH`, `SE`)
    - `packages/builtin-skills-rules/seed_rules.yaml` (Global mandatory & role-exclusive rules)
    - `packages/builtin-skills-rules/seed_skills.yaml` (Common & role-specific CLI skills)
    - `apps/api-server/app/db/seed_runner.py` (Populates `agent_roles`, `rules_registry`, `agent_role_rules`, `skills_registry`, `agent_role_skills`, and computes 768-d embeddings)
  - **Verification Command**: `cd apps/api-server && python -m app.db.seed_runner`

- [ ] **TASK-05** `[THINKING: MEDIUM]` — **Implement LangGraph State Contracts & Claim-Check Artifact Manager**
  - **Implements**: `REQ-002`, `REQ-008` (Section 6.1 & ADR-002 of `MASTER_SPEC.md`)
  - **Target Files**:
    - `apps/api-server/app/orchestrator/state.py` (`PlatformAgentState`, `OrchestratorPlanOutput`, `SubAgentExecutionOutput`, `ArtifactPointer`)
    - `apps/api-server/app/orchestrator/artifact_manager.py` (Stores full Markdown in `shared_artifacts` and returns lightweight 200-word pointer to state)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_artifact_manager.py -v`

- [ ] **TASK-06** `[THINKING: HIGH]` — **Implement Generic Role Runner & LangGraph DAG Supervisor with Circuit Breaker**
  - **Implements**: `REQ-001`, `REQ-002`, `REQ-008`
  - **Target Files**:
    - `apps/api-server/app/orchestrator/role_runner.py` (Executes any built-in or custom role node, handles `NEED_TOOL_CALL` vs `COMPLETED` loop, persists ticket status)
    - `apps/api-server/app/orchestrator/supervisor_graph.py` (Topologically sorts `dag_steps`, dispatches parallel/sequential role nodes, enforces `max_hops = 8` circuit breaker, integrates `AsyncPostgresSaver`)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_supervisor_dag.py -v`

- [ ] **TASK-07** `[THINKING: MEDIUM]` — **Execute Milestone 1 End-to-End Acceptance Suite (`TC-M1-01` to `TC-M1-03`)**
  - **Implements**: `TC-M1-01`, `TC-M1-02`, `TC-M1-03`
  - **Target Files**:
    - `apps/api-server/tests/test_milestone1.py`
  - **Verification Command**: `cd apps/api-server && pytest tests/test_milestone1.py -v`

---

## Milestone 2: Unified Tool Bus, Enterprise MCP Connectors & HITL Gate

- [ ] **TASK-08** `[THINKING: HIGH]` — **Implement AES-256-GCM Token Vault & RBAC/OBO Security Dependencies**
  - **Implements**: `REQ-006`, `REQ-012`
  - **Target Files**:
    - `apps/api-server/app/core/crypto_vault.py` (Encrypts/decrypts `user_connector_tokens` using AES-256-GCM with per-record nonce)
    - `apps/api-server/app/core/security.py` (JWT auth, user context extraction, OBO token retrieval helper)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_crypto_vault.py -v`

- [ ] **TASK-09** `[THINKING: HIGH]` — **Implement HITL Security Gate Interceptor & Checkpoint Resume API**
  - **Implements**: `REQ-007`, `REQ-016` (Section 8 & 9 of `MASTER_SPEC.md`)
  - **Target Files**:
    - `apps/api-server/app/tool_bus/hitl_interceptor.py` (Inspects tool `action_tier`; auto-passes `READ`/`DRAFT`; raises LangGraph `NodeInterrupt` on `COMMIT` after creating `hitl_approval_requests` row)
    - `apps/api-server/app/api/v1_hitl.py` (`POST /api/v1/hitl/{request_id}/decide` supporting `APPROVED`, `MODIFIED` with `user_modified_payload`, and `REJECTED`)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_hitl_flow.py -v`

- [ ] **TASK-10** `[THINKING: MEDIUM]` — **Implement Dynamic Role & Tool RAG Retriever (`pgvector` HNSW)**
  - **Implements**: `REQ-009`
  - **Target Files**:
    - `apps/api-server/app/orchestrator/tool_rag.py` (Queries `agent_roles` and MCP tools using `routing_embedding <=> query_embedding`, enforcing visibility scope and capping at Top-5 tools per turn)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_tool_rag.py -v`

- [ ] **TASK-11** `[THINKING: MEDIUM]` — **Implement Microsoft O365 & Teams Internal MCP Servers**
  - **Implements**: `REQ-006`
  - **Target Files**:
    - `packages/mcp-connectors/mcp_o365/server.py` (`o365_search_messages`, `o365_create_draft`, `o365_send_mail`, `o365_find_meeting_times`, `o365_create_event`, `onedrive_read_file` via MS Graph OBO token)
    - `packages/mcp-connectors/mcp_teams/server.py` (`teams_read_channel_thread`, `teams_send_message`, Adaptive Approval Card sender)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_mcp_o365_teams.py -v`

- [ ] **TASK-12** `[THINKING: MEDIUM]` — **Implement Slack & Generic IMAP/SMTP Internal MCP Servers + Unified Tool Bus**
  - **Implements**: `REQ-006`
  - **Target Files**:
    - `packages/mcp-connectors/mcp_slack/server.py` (`slack_search_messages`, `slack_post_message`)
    - `packages/mcp-connectors/mcp_email_generic/server.py` (`imap_search_unread`, `smtp_send_email`)
    - `apps/api-server/app/tool_bus/bus.py` (`UnifiedToolBus` routing calls across `SERVER_MCP`, `BROWSER_WS_RPC`, `SERVER_SANDBOX_CLI`, and `LOCAL_DAEMON_CLI`)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_mcp_slack_mail.py -v`

- [ ] **TASK-13** `[THINKING: MEDIUM]` — **Execute Milestone 2 End-to-End Acceptance Suite (`TC-M2-01` to `TC-M2-03`)**
  - **Implements**: `TC-M2-01`, `TC-M2-02`, `TC-M2-03`
  - **Target Files**:
    - `apps/api-server/tests/test_milestone2.py`
  - **Verification Command**: `cd apps/api-server && pytest tests/test_milestone2.py -v`

---

## Milestone 3: Web Portal PWA, Self-Service Agent Studio & Browser Local File Bridge

- [ ] **TASK-14** `[THINKING: HIGH]` — **Implement Backend WebSocket Reverse RPC Manager & Stateless Document Parser**
  - **Implements**: `REQ-004`, `REQ-012` (Section 6.3 of `MASTER_SPEC.md`)
  - **Target Files**:
    - `apps/api-server/app/tool_bus/ws_rpc_manager.py` (`WebSocketReverseRPCManager` with strict `requester_user_id == mount_owner_user_id` check and 30s timeout)
    - `apps/api-server/app/tool_bus/doc_parser.py` (In-memory `MarkItDown` conversion for base64 `.docx`/`.xlsx`/`.pdf` + >3,000 token ephemeral chunking into `agent_memories`)
    - `apps/api-server/app/api/ws_client_tools.py` (`WS /api/v1/ws/client-tools/{session_id}`)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_ws_reverse_rpc.py -v`

- [ ] **TASK-15** `[THINKING: MEDIUM]` — **Implement REST & SSE APIs for Chat Streaming, Custom Agent Studio & Ticket Kanban**
  - **Implements**: `REQ-003`, `REQ-010` (Section 9 of `MASTER_SPEC.md`)
  - **Target Files**:
    - `apps/api-server/app/api/v1_chat.py` (`POST /api/v1/chat/sessions/{session_id}/stream` SSE endpoint)
    - `apps/api-server/app/api/v1_agents.py` (`POST /api/v1/agents/generate-spec` Meta-Prompt builder, `POST /api/v1/agents` with `ERR_LOCAL_MOUNT_MUST_BE_PRIVATE` validation, `POST /api/v1/mounts/register`)
    - `apps/api-server/app/api/v1_tickets.py` (Org chart hierarchy & live ticket DAG status endpoints)
    - `apps/api-server/app/main.py`
  - **Verification Command**: `cd apps/api-server && pytest tests/test_api_endpoints.py -v`

- [ ] **TASK-16** `[THINKING: HIGH]` — **Implement Frontend Chromium File System Access Bridge & WebSocket RPC Runner**
  - **Implements**: `REQ-004`, `REQ-012` (Section 6.3 of `MASTER_SPEC.md`)
  - **Target Files**:
    - `apps/web-portal/package.json` (Next.js 15, React 19, TailwindCSS, `@xyflow/react`, `mermaid`, `idb-keyval`, `react-diff-viewer-continued`, `lucide-react`)
    - `apps/web-portal/src/lib/localFsBridge.ts` (`BrowserLocalFsBridge` with `showDirectoryPicker`, `IndexedDB` persistence, path traversal & `.env/.pem` denylist)
    - `apps/web-portal/src/lib/wsClientToolRunner.ts` (Listens for `CLIENT_FS_READ` / `CLIENT_FS_WRITE` over WebSocket and triggers Diff confirmation modal before disk write)
  - **Verification Command**: `cd apps/web-portal && npm install && npx tsc --noEmit`

- [ ] **TASK-17** `[THINKING: MEDIUM]` — **Implement Frontend Split-Screen Chat Workspace, Artifact Preview & Diff Modal**
  - **Implements**: `REQ-007`, `REQ-010`
  - **Target Files**:
    - `apps/web-portal/src/app/chat/page.tsx`
    - `apps/web-portal/src/components/chat/ChatStream.tsx`
    - `apps/web-portal/src/components/chat/HitlApprovalCard.tsx`
    - `apps/web-portal/src/components/artifacts/ArtifactViewer.tsx` (Markdown, Mermaid diagram renderer, Code syntax highlighter)
    - `apps/web-portal/src/components/artifacts/LocalFileDiffModal.tsx` (Red/green diff viewer with `[核准並寫入本機]` button)
  - **Verification Command**: `cd apps/web-portal && npx tsc --noEmit`

- [ ] **TASK-18** `[THINKING: MEDIUM]` — **Implement Frontend Interactive Org Chart (`@xyflow/react`) & Self-Service Agent Studio**
  - **Implements**: `REQ-002`, `REQ-003`, `REQ-010`
  - **Target Files**:
    - `apps/web-portal/src/app/org-chart/page.tsx` (Paperclip-style Org Chart + Live Ticket Kanban)
    - `apps/web-portal/src/app/studio/page.tsx`
    - `apps/web-portal/src/components/studio/AgentMetaWizard.tsx` (1-sentence AI generator + Local Folder Mount binder)
    - `apps/web-portal/src/app/settings/connectors/page.tsx`
  - **Verification Command**: `cd apps/web-portal && npm run build`

- [ ] **TASK-19** `[THINKING: MEDIUM]` — **Execute Milestone 3 End-to-End Acceptance Suite (`TC-M3-01` to `TC-M3-03`)**
  - **Implements**: `TC-M3-01`, `TC-M3-02`, `TC-M3-03`
  - **Target Files**:
    - `apps/api-server/tests/test_milestone3.py`
  - **Verification Command**: `cd apps/api-server && pytest tests/test_milestone3.py -v`

---

## Milestone 4: 24/7 Background Heartbeats, Optional Local Daemon & Zero-Trust Audit

- [ ] **TASK-20** `[THINKING: MEDIUM]` — **Implement Celery 24/7 Atomic Ticket Worker & Scheduled Heartbeat Routines**
  - **Implements**: `REQ-002`, `REQ-011`
  - **Target Files**:
    - `apps/api-server/app/workers/celery_app.py`
    - `apps/api-server/app/workers/ticket_worker.py` (Atomic ticket checkout using `SELECT ... FOR UPDATE SKIP LOCKED`)
    - `apps/api-server/app/workers/heartbeat_cron.py` (Scheduled daily inbox triage & Teams morning brief with graceful offline local-mount fallback)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_workers.py -v`

- [ ] **TASK-21** `[THINKING: MEDIUM]` — **Implement Optional Lightweight Local MCP Daemon for Engineers**
  - **Implements**: `REQ-005`, `REQ-016`
  - **Target Files**:
    - `packages/local-mcp-daemon/daemon.py` (Single-file async WebSocket daemon handling `CLIENT_FS_READ`, `CLIENT_FS_WRITE`, and `DAEMON_EXEC_CLI` when browser is closed)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_local_daemon.py -v`

- [ ] **TASK-22** `[THINKING: HIGH]` — **Perform Multi-Tenant / Cross-User Zero-Trust Security Audit & Hardening**
  - **Implements**: `REQ-012`
  - **Target Files**:
    - `apps/api-server/tests/test_zero_trust_penetration.py` (Verifies User B cannot read/invoke User A's `PRIVATE` agents, OBO tokens, `USER_PRIVATE` memories, or browser/daemon mounts)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_zero_trust_penetration.py -v`

- [ ] **TASK-23** `[THINKING: MEDIUM]` — **Execute Milestone 4 End-to-End Acceptance Suite (`TC-M4-01` to `TC-M4-03`)**
  - **Implements**: `TC-M4-01`, `TC-M4-02`, `TC-M4-03`
  - **Target Files**:
    - `apps/api-server/tests/test_milestone4.py`
  - **Verification Command**: `cd apps/api-server && pytest tests/test_milestone4.py -v`

---

## Milestone 5: Role-Isolated Rules, Progressive Skills & Dual-Target CLI Sandbox

- [ ] **TASK-24** `[THINKING: HIGH]` — **Implement Onion-Layered Prompt Compiler & 2-Stage Progressive Skill Activator**
  - **Implements**: `REQ-013`, `REQ-014` (Section 6.2 of `MASTER_SPEC.md`)
  - **Target Files**:
    - `apps/api-server/app/orchestrator/prompt_compiler.py` (`PromptCompiler.compile_for_role` enforcing strict M:N isolation of `agent_role_rules` and `agent_role_skills`)
    - `apps/api-server/app/orchestrator/skill_activator.py` (Handles `activate_skill(skill_code)` tool call to dynamically transition a skill from Stage-1 manifest to Stage-2 active SOP)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_prompt_compiler_isolation.py -v`

- [ ] **TASK-25** `[THINKING: HIGH]` — **Implement Rootless Docker Sandbox Runner & Parameterized Anti-Injection CLI Executor**
  - **Implements**: `REQ-015`, `REQ-016` (Section 6.4 of `MASTER_SPEC.md`)
  - **Target Files**:
    - `apps/api-server/app/tool_bus/sandbox_runner.py` (`ServerDockerSandboxRunner` with `network_mode="none"`, `mem_limit="512m"`, `pids_limit=64`, `read_only=True`, tmpfs `/workspace`, auto-cleanup)
    - `apps/api-server/app/tool_bus/cli_executor.py` (`SkillCLIExecutor` with JSON schema validation, `shlex.quote` escaping, `FORBIDDEN_CLI_TOKENS` guard, and automatic browser file sync)
    - `packages/builtin-skills-rules/scripts/validate_openapi.py`
    - `packages/builtin-skills-rules/scripts/fin_calculator.py`
  - **Verification Command**: `cd apps/api-server && pytest tests/test_cli_sandbox_security.py -v`

- [ ] **TASK-26** `[THINKING: MEDIUM]` — **Implement Rules & Skills Management APIs**
  - **Implements**: `REQ-013`, `REQ-014`
  - **Target Files**:
    - `apps/api-server/app/api/v1_rules_skills.py` (`GET/POST /api/v1/rules`, `GET/POST /api/v1/skills`, and role-binding endpoints)
  - **Verification Command**: `cd apps/api-server && pytest tests/test_api_rules_skills.py -v`

- [ ] **TASK-27** `[THINKING: MEDIUM]` — **Implement Frontend Rule/Skill Binding Selectors & Live ANSI Terminal Output Card**
  - **Implements**: `REQ-010`, `REQ-013`, `REQ-014`, `REQ-015`
  - **Target Files**:
    - `apps/web-portal/src/components/studio/RuleBindingSelector.tsx`
    - `apps/web-portal/src/components/studio/SkillEditorModal.tsx`
    - `apps/web-portal/src/components/artifacts/TerminalOutputCard.tsx` (Displays rendered CLI command, execution target badge, exit code, and stdout/stderr logs)
  - **Verification Command**: `cd apps/web-portal && npm run build`

- [ ] **TASK-28** `[THINKING: MEDIUM]` — **Execute Milestone 5 & Full Platform Regression Suite (`TC-M5-01` to `TC-M5-04`)**
  - **Implements**: `TC-M5-01`, `TC-M5-02`, `TC-M5-03`, `TC-M5-04`
  - **Target Files**:
    - `apps/api-server/tests/test_milestone5.py`
  - **Verification Command**: `cd apps/api-server && pytest -v`
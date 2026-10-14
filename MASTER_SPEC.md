# Enterprise Multi-Agent Platform - Master Architecture & Implementation Specification (v3.0 Unified Edition)

- **Document ID**: `EAMP-MASTER-SPEC-2026-V3.0`
- **Target Coding Agent**: **Gemini 4 Argon (`gemini-4-argon`)** (via Cursor, Google Antigravity, OpenCode, or Direct API)
- **Target On-Premise Runtime LLM**: Google **Gemma 4** (served via **SGLang** or **vLLM**) + **google/embeddinggemma-2** (768-d)
- **License Policy**: **100% Commercial-Safe Open Source ONLY** (MIT, Apache-2.0, BSD-3, PostgreSQL License). Strictly NO AGPLv3, GPL, SSPL, or Fair-code (Dify/n8n) dependencies in core runtime.

---

## 0. Meta-Directives for Coding Agent (`gemini-4-argon`)

When implementing this repository, the Coding Agent MUST obey these execution rules:
1. **Implicit Cache Optimization**: Always keep this `MASTER_SPEC.md` pinned at the beginning of the context window so `gemini-4-argon` automatically triggers **Implicit Caching (95% input token discount)**.
2. **Reasoning Effort (`thinking_level`) Protocol**:
   - Follow the explicit **`[建議思考等級: MEDIUM]`** or **`[建議思考等級: HIGH]`** tag marked on each task in **Section 11**.
   - When running in **`HIGH`** mode, set `max_output_tokens >= 131072` and request timeout to at least `900s` so deep architectural reasoning does not truncate generated code.
   - When running in **`MEDIUM`** mode, set `max_output_tokens = 65536` for fast, deterministic file generation.
3. **Zero Stubs Policy**: Never output `# TODO: implement later`, `pass`, or mock placeholders. Every generated file must be production-ready, fully typed (Python 3.12 Type Hints / TypeScript Strict Mode), and annotated with `# Implements: REQ-XXX`.

---

## 1. End-to-End Requirement Traceability Matrix (RTM: `REQ-001` to `REQ-016`)

Every module, database table, API endpoint, and acceptance test case in this specification traces back to these 16 core requirements:

| REQ-ID | Category | Detailed Requirement Description | Mapped Module ID | Mapped DB Tables | Test Case ID |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-001** | **Multi-Role Presets** | Provide 7 built-in enterprise roles: Master Orchestrator (`ORCH`), `CEO`, Project Manager (`PM`), Financial Expert (`FIN`), System Analyst (`SA`), Architecture Analyst (`ARCH`), Senior Engineer (`SE`). | `MOD-ORCH`, `MOD-ROLES` | `agent_roles` | `TC-M1-01` |
| **REQ-002** | **Hierarchical DAG Delegation** | `ORCH` decomposes requests into a Task DAG and delegates sub-tasks to roles using Paperclip-style atomic ticket locking, Goal Ancestry, and `max_hops = 8` circuit breaking. | `MOD-ORCH`, `MOD-TICKET` | `tasks_tickets`, `shared_artifacts` | `TC-M1-02` |
| **REQ-003** | **Self-Service Agent Builder** | Allow end-users to create custom Agents via Web UI (with Gemma 4 Meta-Prompt assistance) and publish across 3 scopes (`PRIVATE`, `DEPARTMENT`, `GLOBAL`). | `MOD-STUDIO`, `MOD-ORCH` | `agent_roles` | `TC-M3-01` |
| **REQ-004** | **Web Local File Access** | Enable the Web Portal to read/write user-authorized local folders directly via Chromium **W3C File System Access API** + **WebSocket Reverse RPC** without installing a desktop app. | `MOD-LOCAL-FS`, `MOD-WS-RPC` | `local_workspace_mounts` | `TC-M3-02` |
| **REQ-005** | **Optional Local Daemon** | Provide a unified interface so engineers can optionally run a lightweight 5MB Local MCP Daemon for 24/7 offline local file access and local CLI/Git execution. | `MOD-LOCAL-FS`, `MOD-MCP-GW` | `local_workspace_mounts` | `TC-M4-02` |
| **REQ-006** | **Enterprise Connectors** | Integrate Microsoft Office 365 (Outlook Mail, Calendar, OneDrive), Microsoft Teams, Slack, and generic IMAP/SMTP Email via standardized internal MCP servers. | `MOD-MCP-GW`, `MOD-CONN` | `user_connector_tokens` | `TC-M2-01` |
| **REQ-007** | **HITL Security Gate** | Classify all tool/CLI calls into `READ`, `DRAFT`, and `COMMIT`. Automatically intercept `COMMIT` actions (sending mail, posting messages, writing local files, mutating CLI) for user approval. | `MOD-HITL`, `MOD-ORCH` | `hitl_approval_requests` | `TC-M2-02` |
| **REQ-008** | **On-Premise Gemma 4 Optimization** | Guarantee 99.9% valid JSON tool calls and handoffs on local Gemma 4 using SGLang FSM Constrained Decoding, RadixAttention KV-cache sharing, and Artifact Pointers (Claim-Check pattern). | `MOD-LLM-GW`, `MOD-ORCH` | `shared_artifacts` | `TC-M1-03` |
| **REQ-009** | **Dynamic Role & Tool RAG** | Use local `google/embeddinggemma-2` + `pgvector` to dynamically inject only Top-K relevant roles, tools, and skills per turn. | `MOD-RAG`, `MOD-ORCH` | `agent_roles`, `skills_registry` | `TC-M2-03` |
| **REQ-010** | **AionUi Split Workspace** | Provide a Web PWA featuring Multi-Agent Chat, Interactive Org Chart / Ticket DAG viewer, and a right-hand Artifact Preview, Diff Confirmation & ANSI Terminal viewer. | `MOD-WEB-UI` | `shared_artifacts` | `TC-M3-03` |
| **REQ-011** | **24/7 Background Heartbeats** | Support scheduled recurring routines (e.g., daily 08:30 inbox triage & Teams morning brief) running asynchronously via Celery Beat + Redis. | `MOD-WORKER` | `tasks_tickets` | `TC-M4-01` |
| **REQ-012** | **Enterprise Zero-Trust & RBAC** | Enforce On-Behalf-Of (OBO) per-user OAuth2 tokens, AES-256-GCM encryption, strict tenant/user memory isolation, and local path traversal/denylist protections. | `MOD-SEC` | `users`, `user_connector_tokens`, `agent_memories` | `TC-M4-03` |
| **REQ-013** | **Hierarchical & Isolated Rules** | Support `GLOBAL_MANDATORY`, `DEPARTMENT_SHARED`, and `ROLE_EXCLUSIVE` rules. Exclusive rules bound to Agent A MUST NEVER leak into Agent B's prompt context. | `MOD-RULE-ENG`, `MOD-ORCH` | `rules_registry`, `agent_role_rules` | `TC-M5-01` |
| **REQ-014** | **Progressive-Disclosure Skills** | Allow binding common or exclusive Skills to agents. Inject compact Stage-1 manifests (~50 tokens) initially; load full Stage-2 SOP and CLI schemas only when activated. | `MOD-SKILL-ENG`, `MOD-ORCH` | `skills_registry`, `agent_role_skills` | `TC-M5-02` |
| **REQ-015** | **Server Sandbox CLI (Web Zero-Install)** | Enable Skills to run CLI tools and Python/Node/Bash scripts inside an isolated rootless container (`SERVER_SANDBOX_CLI`), automatically syncing needed files from Browser Local Mounts. | `MOD-CLI-EXEC`, `MOD-MCP-GW` | `cli_execution_logs` | `TC-M5-03` |
| **REQ-016** | **Local Daemon CLI & Anti-Injection** | Enable Skills to target the user's endpoint CLI (`LOCAL_DAEMON_CLI`), enforce parameterized `shlex.quote` templates + JSON schema validation, and gate `COMMIT` CLI calls with HITL. | `MOD-CLI-EXEC`, `MOD-HITL` | `cli_execution_logs`, `hitl_approval_requests` | `TC-M5-04` |

---

## 2. Architecture Decision Records (ADR) & Unified System Topology

### ADR Summary
- **ADR-001 (Web-First PWA + Browser Reverse RPC)**: Use a centralized Next.js 15 PWA paired with Chromium's native `File System Access API` (`showDirectoryPicker`) + `IndexedDB` handle persistence + WebSocket Reverse RPC. 90% of users get zero-install local file reading/writing; 10% power users (engineers) can optionally run a 5MB `Local MCP Daemon` for offline background access and local Git/CLI.
- **ADR-002 (Claim-Check Artifact Pointer Pattern)**: Sub-agents store full outputs (>500 tokens) in `shared_artifacts` and only pass `{ artifact_id, title, summary_200_words }` in LangGraph state to protect local Gemma 4 from context overflow.
- **ADR-003 (Onion-Layered Prompt Compiler for SGLang KV Cache)**: Compile System Prompts in deterministic order: `[Layer 1: Global/Dept Rules] -> [Layer 2: Role Base Prompt] -> [Layer 3: Role-Exclusive Rules] -> [Layer 4: Stage-1 Bound Skill Catalog] -> [Layer 5: Stage-2 Active Skill SOPs]`. Maximizes SGLang RadixAttention prefix cache sharing while guaranteeing strict isolation between agents.
- **ADR-004 (Dual-Target Parameterized CLI Execution)**: Skills never execute raw arbitrary shell strings. Every CLI Skill defines a `command_template` with `{{param}}` placeholders validated against a strict JSON Schema and escaped with `shlex.quote()`, routed to either an ephemeral network-isolated Docker container (`SERVER_SANDBOX_CLI`) or the user's endpoint daemon (`LOCAL_DAEMON_CLI`).

### Unified System Topology Diagram (Mermaid)
~~~mermaid
flowchart TB
    subgraph Client_Boundary ["員工終端邊界 (User Endpoint - Zero Install Web PWA)"]
        UI["Next.js 15 Web Portal / Teams Tab\n(Chat + Org Chart + Studio + Diff/Terminal Preview)"]
        FS_API["Browser File System Access API\n(IndexedDB DirectoryHandle + Denylist Filter)"]
        OPT_DAEMON["選配: 輕量 Local MCP Daemon\n(工程師本機離線檔案 / Git / CLI)"]
        UI <--> FS_API
    end

    subgraph Server_Boundary ["企業機房內網邊界 (On-Premise Enterprise Core)"]
        API_GW["FastAPI Gateway\n(REST + SSE Stream + WebSocket RPC Hub)"]
        ORCH["LangGraph Supervisor & DAG Engine\n(Max-Hops=8 + Atomic Ticket Lock + Claim-Check)"]
        COMPILER["Onion Prompt Compiler\n(Rule Isolation + 2-Stage Skill Loader)"]
        HITL["HITL Security Interceptor\n(Read / Draft / Commit Gate)"]
        TOOL_BUS["Unified Tool & CLI Execution Bus"]
        SANDBOX["Server Rootless Docker Sandbox\n(SERVER_SANDBOX_CLI - Zero-Install Web CLI)"]
        WORKER["Celery + Redis 24/7 Worker\n(Scheduled Heartbeats & Async Tickets)"]

        subgraph Role_Pool ["角色代理池 (7 Built-in + Custom Agents)"]
            R_ORCH["ORCH (主代理)"]
            R_EXPERTS["CEO / PM / FIN / SA / ARCH / SE"]
            R_CUSTOM["使用者自建 Agent (Private / Dept / Global)"]
        end

        subgraph Data_And_AI ["本地算力與儲存底座 (On-Premise AI & Storage)"]
            SGLANG["SGLang / vLLM Cluster\n(Gemma 4 + FSM JSON Constrained Decoding)"]
            EMBED["Embedding Service\n(google/embeddinggemma-2)"]
            PG[("PostgreSQL 16 + pgvector\n(13 Tables: Roles, Rules, Skills, Tickets, Vault)")]
        end

        subgraph MCP_Connectors ["企業外部連接器 (Internal MCP Servers)"]
            MCP_O365["mcp-o365 (Outlook / Calendar / OneDrive)"]
            MCP_TEAMS["mcp-teams (MS Teams Bot & Approval Cards)"]
            MCP_SLACK["mcp-slack (Slack Bolt Channels & DMs)"]
            MCP_MAIL["mcp-mail (Generic IMAP / SMTP)"]
        end
    end

    UI <==>|"1. HTTPS / SSE"| API_GW
    FS_API <==>|"2. WSS Reverse RPC (本機檔案讀寫)"| TOOL_BUS
    OPT_DAEMON -.->|"3. WSS Tunnel (LOCAL_DAEMON_CLI)"| TOOL_BUS

    API_GW --> ORCH
    WORKER --> ORCH
    ORCH <--> COMPILER
    COMPILER <--> Role_Pool
    ORCH <--> SGLANG
    ORCH <--> EMBED
    ORCH <--> PG
    Role_Pool --> HITL
    HITL --> TOOL_BUS
    TOOL_BUS --> MCP_Connectors
    TOOL_BUS --> SANDBOX
~~~

---

## 3. Commercial-Safe Tech Stack & License BOM

| Layer | Package / Technology | License | Role in Platform |
| :--- | :--- | :--- | :--- |
| **LLM Serving** | `SGLang` (or `vLLM`) + `Gemma 4` | Apache-2.0 | Local inference with RadixAttention KV cache & FSM JSON schema enforcement. |
| **Embeddings** | `google/embeddinggemma-2` | Apache-2.0 | Local 768-d vector embeddings for Role routing, Tool RAG, Skill matching, and Memory. |
| **Orchestration** | `langgraph`, `langgraph-checkpoint-postgres`, `pydantic` v2 | MIT | Stateful DAG orchestration, HITL checkpoint interrupts, and strict data contracts. |
| **Backend API** | `FastAPI`, `uvicorn`, `websockets`, `SQLAlchemy` 2.0, `alembic` | MIT | Async REST, SSE streaming, WebSocket Reverse RPC, and async ORM. |
| **CLI Sandbox & Docs** | `docker` (Python SDK), `markitdown`, `jsonschema` | Apache-2.0 / MIT | Ephemeral rootless container CLI execution and stateless `.docx/.xlsx/.pdf` parsing. |
| **Background Queue** | `celery`, `redis` | BSD-3 | 24/7 cron heartbeats and asynchronous ticket execution. |
| **Database** | `PostgreSQL 16` + `pgvector` | PostgreSQL | Unified relational, JSONB artifact, and HNSW vector storage. |
| **MCP Connectors** | `mcp` (Python SDK), `msgraph-sdk`, `slack-bolt` | MIT | Standardized enterprise connectors with per-user OBO token isolation. |
| **Frontend Web UI** | `Next.js 15`, `React 19`, `TailwindCSS`, `Shadcn UI`, `idb-keyval` | MIT | Web-First PWA, Browser File System Access bridge, and Agent Studio. |
| **Visualization** | `@xyflow/react` (React Flow), `mermaid`, `react-diff-viewer-continued` | MIT | Interactive Org Chart, live DAG tracker, architecture diagrams, and File Diff viewer. |

---

## 4. Complete Modular Monorepo Directory Structure

~~~text
enterprise-agent-platform/
├── MASTER_SPEC.md                              # This unified master specification
├── docker-compose.yml                          # PostgreSQL 16 (pgvector), Redis 7, Sandbox Image, API, Worker, Web
├── .env.example
├── apps/
│   ├── api-server/                             # [Backend] Python 3.12 + FastAPI
│   │   ├── pyproject.toml
│   │   ├── alembic/                            # Alembic migrations (0001_unified_schema.py)
│   │   ├── tests/                              # Pytest suite (TC-M1-01 to TC-M5-04)
│   │   └── app/
│   │       ├── main.py                         # FastAPI entry, lifespan, CORS, routers
│   │       ├── core/                           # [MOD-SEC] Config, OAuth2 OBO, AES-256-GCM Vault
│   │       │   ├── config.py
│   │       │   ├── crypto_vault.py
│   │       │   └── security.py
│   │       ├── db/                             # [Database] 13 SQLAlchemy 2.0 Models & Seeders
│   │       │   ├── session.py
│   │       │   ├── models.py
│   │       │   └── seed_runner.py              # Idempotent seeder for Roles, Rules, and Skills
│   │       ├── llm/                            # [MOD-LLM-GW] SGLang & Embedding Clients
│   │       │   ├── gemma_client.py
│   │       │   └── embedding_client.py
│   │       ├── orchestrator/                   # [MOD-ORCH, MOD-RULE-ENG, MOD-SKILL-ENG, MOD-RAG]
│   │       │   ├── state.py                    # PlatformAgentState & Pydantic JSON schemas
│   │       │   ├── prompt_compiler.py          # Onion-layered Rule & Skill isolation compiler
│   │       │   ├── tool_rag.py                 # Dynamic Top-K Role, Tool & Skill vector retriever
│   │       │   ├── artifact_manager.py         # Claim-Check pointer storage & section reader
│   │       │   ├── role_runner.py              # Generic execution node for built-in & custom roles
│   │       │   └── supervisor_graph.py         # LangGraph DAG scheduler & max_hops=8 circuit breaker
│   │       ├── tool_bus/                       # [MOD-MCP-GW, MOD-WS-RPC, MOD-CLI-EXEC, MOD-HITL]
│   │       │   ├── bus.py                      # Unified dispatcher (Server MCP / Browser WS / CLI)
│   │       │   ├── hitl_interceptor.py         # Read / Draft / Commit security gate
│   │       │   ├── ws_rpc_manager.py           # Browser & Daemon WebSocket Reverse RPC pool
│   │       │   ├── doc_parser.py               # Stateless MarkItDown binary-to-Markdown converter
│   │       │   ├── cli_executor.py             # Parameterized shlex anti-injection CLI router
│   │       │   └── sandbox_runner.py           # Rootless Docker container runner for Web CLI skills
│   │       ├── workers/                        # [MOD-WORKER] Celery 24/7 Background Engine
│   │       │   ├── celery_app.py
│   │       │   ├── ticket_worker.py
│   │       │   └── heartbeat_cron.py
│   │       └── api/                            # REST, SSE & WebSocket Endpoints
│   │           ├── v1_chat.py
│   │           ├── v1_agents.py
│   │           ├── v1_rules_skills.py
│   │           ├── v1_tickets.py
│   │           ├── v1_hitl.py
│   │           └── ws_client_tools.py
│   │
│   └── web-portal/                             # [Frontend - MOD-WEB-UI] Next.js 15 App Router
│       ├── package.json
│       └── src/
│           ├── app/
│           │   ├── chat/page.tsx               # Split-screen Multi-Agent Workspace
│           │   ├── studio/page.tsx             # Self-Service Agent, Rule & Skill Studio
│           │   ├── org-chart/page.tsx          # Interactive Org Chart & Ticket Kanban
│           │   └── settings/connectors/page.tsx# O365/Slack OAuth & Local Folder Mount Manager
│           ├── components/
│           │   ├── chat/                       # ChatStream, RoleBadge, HitlApprovalCard
│           │   ├── artifacts/                  # ArtifactViewer, LocalFileDiffModal, TerminalOutputCard
│           │   └── studio/                     # AgentMetaWizard, RuleBindingSelector, SkillEditorModal
│           └── lib/
│               ├── localFsBridge.ts            # W3C File System Access API + IndexedDB manager
│               └── wsClientToolRunner.ts       # Browser Reverse RPC listener & execution sandbox
│
└── packages/
    ├── mcp-connectors/                         # [MOD-CONN] Internal Enterprise MCP Servers
    │   ├── mcp_o365/
    │   ├── mcp_teams/
    │   ├── mcp_slack/
    │   └── mcp_email_generic/
    ├── builtin-roles/                          # [MOD-ROLES] 7 Core Roles Seed Config
    │   └── seed_roles.yaml
    ├── builtin-skills-rules/                   # [MOD-RULE-ENG & MOD-SKILL-ENG] Default Rules & Skills
    │   ├── seed_rules.yaml
    │   ├── seed_skills.yaml
    │   └── scripts/                            # Bundled Python scripts mounted into Server Sandbox
    │       ├── validate_openapi.py
    │       └── fin_calculator.py
    └── local-mcp-daemon/                       # [Optional] Lightweight CLI/File bridge for Engineers
        └── daemon.py
~~~

---

## 5. Complete Unified Database Schema (All 13 Tables in FK-Safe Order)

Implement in `apps/api-server/app/db/models.py` and Alembic migration `0001_unified_schema.py`:

~~~sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Table 1: users (REQ-012)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    department VARCHAR(100) NOT NULL, -- e.g., 'TS30', 'RD', 'FINANCE', 'EXEC'
    job_title VARCHAR(100),
    sso_subject_id VARCHAR(255) UNIQUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 2: local_workspace_mounts (REQ-004, REQ-005)
CREATE TABLE local_workspace_mounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mount_alias VARCHAR(100) NOT NULL,
    provider_type VARCHAR(30) NOT NULL DEFAULT 'BROWSER_FS_API', -- 'BROWSER_FS_API' | 'LOCAL_MCP_DAEMON' | 'ONEDRIVE_MIRROR'
    browser_handle_key VARCHAR(255), -- IndexedDB key storing FileSystemDirectoryHandle
    permission_mode VARCHAR(30) NOT NULL DEFAULT 'READ_WRITE_WITH_CONFIRM', -- 'READ_ONLY' | 'READ_WRITE_WITH_CONFIRM'
    allowed_extensions JSONB NOT NULL DEFAULT '[".md", ".txt", ".docx", ".xlsx", ".pdf", ".py", ".ts", ".json", ".sql", ".yaml", ".yml"]',
    cached_file_tree JSONB NOT NULL DEFAULT '[]',
    last_synced_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 3: agent_roles (REQ-001, REQ-003, REQ-009)
CREATE TABLE agent_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(64) UNIQUE NOT NULL, -- 'ORCH', 'CEO', 'PM', 'FIN', 'SA', 'ARCH', 'SE', or 'CUSTOM_*'
    name VARCHAR(120) NOT NULL,
    department VARCHAR(100) NOT NULL DEFAULT 'GLOBAL',
    reports_to_id UUID REFERENCES agent_roles(id) ON DELETE SET NULL,
    creator_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    visibility_scope VARCHAR(20) NOT NULL DEFAULT 'PRIVATE', -- 'PRIVATE' | 'DEPARTMENT' | 'GLOBAL'
    approval_status VARCHAR(20) NOT NULL DEFAULT 'APPROVED', -- 'DRAFT' | 'PENDING_REVIEW' | 'APPROVED'
    system_prompt TEXT NOT NULL,
    routing_description TEXT NOT NULL,
    routing_embedding VECTOR(768),
    output_json_schema JSONB NOT NULL,
    allowed_tool_namespaces JSONB NOT NULL DEFAULT '[]',
    bound_local_mount_id UUID REFERENCES local_workspace_mounts(id) ON DELETE SET NULL,
    model_params JSONB NOT NULL DEFAULT '{"model": "gemma-4-27b-it", "temperature": 0.2, "max_tokens": 4096}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_local_mount_private CHECK (
        bound_local_mount_id IS NULL OR visibility_scope = 'PRIVATE'
    )
);

CREATE INDEX idx_agent_roles_embedding ON agent_roles USING hnsw (routing_embedding vector_cosine_ops);

-- Table 4: rules_registry (REQ-013)
CREATE TABLE rules_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(120) NOT NULL,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'ROLE_EXCLUSIVE', -- 'GLOBAL_MANDATORY' | 'DEPARTMENT_SHARED' | 'ROLE_EXCLUSIVE'
    department VARCHAR(100),
    creator_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    priority INT NOT NULL DEFAULT 100,
    rule_content_markdown TEXT NOT NULL,
    glob_trigger VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 5: agent_role_rules (REQ-013 Strict M:N Isolation)
CREATE TABLE agent_role_rules (
    role_id UUID NOT NULL REFERENCES agent_roles(id) ON DELETE CASCADE,
    rule_id UUID NOT NULL REFERENCES rules_registry(id) ON DELETE CASCADE,
    is_mandatory BOOLEAN DEFAULT TRUE,
    bound_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (role_id, rule_id)
);

-- Table 6: skills_registry (REQ-014, REQ-015, REQ-016)
CREATE TABLE skills_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(120) NOT NULL,
    visibility_scope VARCHAR(30) NOT NULL DEFAULT 'GLOBAL', -- 'GLOBAL' | 'DEPARTMENT' | 'PRIVATE'
    department VARCHAR(100),
    creator_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    trigger_description VARCHAR(300) NOT NULL,
    trigger_embedding VECTOR(768),
    sop_markdown TEXT NOT NULL,
    execution_mode VARCHAR(30) NOT NULL DEFAULT 'PROMPT_ONLY', -- 'PROMPT_ONLY' | 'SERVER_SANDBOX_CLI' | 'LOCAL_DAEMON_CLI' | 'MCP_TOOL_COMBO'
    cli_config JSONB DEFAULT NULL,
    required_tool_namespaces JSONB NOT NULL DEFAULT '[]',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_skills_trigger_vec ON skills_registry USING hnsw (trigger_embedding vector_cosine_ops);

-- Table 7: agent_role_skills (REQ-014 Strict M:N Isolation)
CREATE TABLE agent_role_skills (
    role_id UUID NOT NULL REFERENCES agent_roles(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES skills_registry(id) ON DELETE CASCADE,
    auto_activate BOOLEAN DEFAULT FALSE,
    bound_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (role_id, skill_id)
);

-- Table 8: shared_artifacts (REQ-002, REQ-008, REQ-010 Claim-Check Store)
CREATE TABLE shared_artifacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL,
    producer_role_code VARCHAR(64) NOT NULL,
    artifact_type VARCHAR(40) NOT NULL, -- 'STRATEGY_MEMO' | 'PROJECT_PLAN_WBS' | 'FINANCIAL_MODEL' | 'REQUIREMENT_SPEC' | 'ARCH_DIAGRAM' | 'CODE_DIFF' | 'EMAIL_DRAFT' | 'LOCAL_FILE_EXTRACT'
    title VARCHAR(255) NOT NULL,
    summary_200_words TEXT NOT NULL,
    content_body TEXT NOT NULL,
    structured_metadata JSONB DEFAULT '{}',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 9: tasks_tickets (REQ-002, REQ-011 Paperclip Atomic Ticket & Goal Ancestry)
CREATE TABLE tasks_tickets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL,
    parent_ticket_id UUID REFERENCES tasks_tickets(id) ON DELETE CASCADE,
    requester_user_id UUID NOT NULL REFERENCES users(id),
    assigned_role_code VARCHAR(64) NOT NULL REFERENCES agent_roles(code),
    title VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING', -- 'PENDING' | 'IN_PROGRESS' | 'WAITING_HITL' | 'COMPLETED' | 'FAILED' | 'CIRCUIT_BROKEN'
    hop_count INT NOT NULL DEFAULT 0,
    max_hops INT NOT NULL DEFAULT 8,
    token_budget INT NOT NULL DEFAULT 16000,
    tokens_consumed INT NOT NULL DEFAULT 0,
    locked_by_worker VARCHAR(100),
    locked_at TIMESTAMPTZ,
    goal_ancestry JSONB NOT NULL DEFAULT '[]',
    input_instructions TEXT NOT NULL,
    input_artifact_ids JSONB NOT NULL DEFAULT '[]',
    output_artifact_id UUID REFERENCES shared_artifacts(id),
    error_log TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Table 10: hitl_approval_requests (REQ-007, REQ-016)
CREATE TABLE hitl_approval_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticket_id UUID NOT NULL REFERENCES tasks_tickets(id) ON DELETE CASCADE,
    session_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    executing_role_code VARCHAR(64) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    execution_target VARCHAR(30) NOT NULL, -- 'SERVER_MCP' | 'BROWSER_WS_RPC' | 'SERVER_SANDBOX_CLI' | 'LOCAL_DAEMON_CLI'
    action_tier VARCHAR(20) NOT NULL DEFAULT 'COMMIT',
    preview_title VARCHAR(255) NOT NULL,
    proposed_payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- 'PENDING' | 'APPROVED' | 'MODIFIED' | 'REJECTED'
    user_modified_payload JSONB,
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 11: cli_execution_logs (REQ-015, REQ-016)
CREATE TABLE cli_execution_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL,
    ticket_id UUID REFERENCES tasks_tickets(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    executing_role_code VARCHAR(64) NOT NULL,
    skill_code VARCHAR(64) NOT NULL REFERENCES skills_registry(code),
    execution_target VARCHAR(30) NOT NULL, -- 'SERVER_SANDBOX_CLI' | 'LOCAL_DAEMON_CLI'
    rendered_command TEXT NOT NULL,
    working_directory VARCHAR(255),
    exit_code INT,
    stdout_preview TEXT,
    stderr_preview TEXT,
    duration_ms INT,
    hitl_request_id UUID REFERENCES hitl_approval_requests(id),
    executed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 12: user_connector_tokens (REQ-006, REQ-012 AES-256-GCM OAuth Vault)
CREATE TABLE user_connector_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(40) NOT NULL, -- 'MICROSOFT_365' | 'SLACK' | 'GENERIC_IMAP'
    encrypted_access_token BYTEA NOT NULL,
    encrypted_refresh_token BYTEA,
    scopes JSONB NOT NULL DEFAULT '[]',
    expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, provider)
);

-- Table 13: agent_memories (REQ-004, REQ-009, REQ-012 3-Tier & Ephemeral File Chunks)
CREATE TABLE agent_memories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    memory_scope VARCHAR(30) NOT NULL, -- 'USER_PRIVATE' | 'DEPARTMENT_SHARED' | 'ORG_GLOBAL' | 'EPHEMERAL_LOCAL_FILE'
    owner_user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    department VARCHAR(100),
    session_id UUID,
    source_reference VARCHAR(255),
    content TEXT NOT NULL,
    embedding VECTOR(768) NOT NULL,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agent_memories_vec ON agent_memories USING hnsw (embedding vector_cosine_ops);
~~~

---

## 6. Core Engine Specifications & Reference Implementations

### 6.1 Core Engine 1: Gemma 4 + SGLang Constrained Decoding & LangGraph State (`MOD-LLM-GW`, `MOD-ORCH`)

#### `apps/api-server/app/llm/gemma_client.py`
~~~python
# Implements: REQ-008 (SGLang Finite State Machine JSON Schema Enforcement for Gemma 4)
from typing import Type, TypeVar
from pydantic import BaseModel
from openai import AsyncOpenAI
from app.core.config import settings

T = TypeVar("T", bound=BaseModel)

class GemmaSGLangClient:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(
            base_url=settings.SGLANG_BASE_URL, # e.g., "http://sglang-gemma4:30000/v1"
            api_key=settings.SGLANG_API_KEY
        )

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[dict],
        response_model: Type[T],
        model_name: str = "gemma-4-27b-it",
        temperature: float = 0.15
    ) -> T:
        schema = response_model.model_json_schema()
        response = await self.client.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": system_prompt}, *messages],
            temperature=temperature,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": schema,
                    "strict": True
                }
            }
        )
        raw_json = response.choices[0].message.content or "{}"
        return response_model.model_validate_json(raw_json)
~~~

#### `apps/api-server/app/orchestrator/state.py`
~~~python
# Implements: REQ-002, REQ-008, REQ-014 (DAG State, Claim-Check Pointers, Progressive Skill Activation)
from typing import TypedDict, Annotated, List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
import operator

class ArtifactPointer(BaseModel):
    artifact_id: str
    producer_role: str
    title: str
    artifact_type: str
    summary_200_words: str

class DAGTaskNode(BaseModel):
    step_id: int = Field(..., description="1-based step ID")
    target_role_code: str = Field(..., description="Target role code from candidate pool")
    task_title: str = Field(..., description="Concise ticket title")
    detailed_instructions: str = Field(..., description="Expected deliverable instructions")
    depends_on_steps: List[int] = Field(default_factory=list)
    required_mount_or_connectors: List[str] = Field(default_factory=list)

class OrchestratorPlanOutput(BaseModel):
    intent_mode: Literal["DIRECT_ANSWER", "DELEGATE_DAG"]
    reasoning: str
    goal_statement: str
    direct_response_to_user: Optional[str] = None
    dag_steps: List[DAGTaskNode] = Field(default_factory=list)

class SubAgentToolCall(BaseModel):
    tool_name: str = Field(..., description="MCP tool name, 'activate_skill', or 'execute_skill_cli'")
    arguments: Dict[str, Any] = Field(default_factory=dict)

class SubAgentExecutionOutput(BaseModel):
    execution_status: Literal["COMPLETED", "NEED_TOOL_CALL", "REQUEST_CLARIFICATION"]
    thought_process: str
    tool_calls: List[SubAgentToolCall] = Field(default_factory=list)
    artifact_title: Optional[str] = None
    artifact_type: Optional[Literal[
        "STRATEGY_MEMO", "PROJECT_PLAN_WBS", "FINANCIAL_MODEL",
        "REQUIREMENT_SPEC", "ARCH_DIAGRAM", "CODE_DIFF", "EMAIL_DRAFT"
    ]] = None
    summary_200_words: Optional[str] = None
    full_markdown_content: Optional[str] = None
    handoff_notes_for_next_role: Optional[str] = None

class PlatformAgentState(TypedDict):
    session_id: str
    user_id: str
    user_department: str
    original_user_query: str
    goal_ancestry: List[str]
    hop_count: int
    max_hops: int
    dag_plan: List[Dict[str, Any]]
    completed_step_ids: List[int]
    artifact_pointers: Annotated[List[Dict[str, Any]], operator.add]
    activated_skills_by_role: Dict[str, List[str]] # role_code -> list of activated skill_codes
    active_ticket_id: Optional[str]
    pending_hitl_request_id: Optional[str]
    final_synthesis: Optional[str]
~~~

---

### 6.2 Core Engine 2: Onion-Layered Rule & Skill Isolation Compiler (`MOD-RULE-ENG`, `MOD-SKILL-ENG`)

#### `apps/api-server/app/orchestrator/prompt_compiler.py`
~~~python
# Implements: REQ-013, REQ-014 (Strict M:N Rule/Skill Isolation & 2-Stage Progressive Skill Loading)
from typing import List, Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import AgentRole, RuleRegistry, AgentRoleRule, SkillRegistry, AgentRoleSkill

class CompiledRoleContext:
    def __init__(self, system_prompt: str, active_skills: List[SkillRegistry]) -> None:
        self.system_prompt = system_prompt
        self.active_skills = active_skills

class PromptCompiler:
    @staticmethod
    async def compile_for_role(
        db: AsyncSession,
        role: AgentRole,
        user_department: str,
        activated_skill_codes: Optional[List[str]] = None
    ) -> CompiledRoleContext:
        activated_skill_codes = activated_skill_codes or []

        # 1. Global Mandatory + Department Rules (Deterministic order for SGLang Prefix Cache)
        global_dept_stmt = (
            select(RuleRegistry)
            .where(
                RuleRegistry.is_active.is_(True),
                or_(
                    RuleRegistry.scope_type == "GLOBAL_MANDATORY",
                    (RuleRegistry.scope_type == "DEPARTMENT_SHARED") & (RuleRegistry.department == user_department)
                )
            )
            .order_by(RuleRegistry.priority.asc(), RuleRegistry.code.asc())
        )
        shared_rules = (await db.execute(global_dept_stmt)).scalars().all()

        # 2. Role-Exclusive Rules (Strictly filtered by AgentRoleRule.role_id == role.id)
        role_rules_stmt = (
            select(RuleRegistry)
            .join(AgentRoleRule, AgentRoleRule.rule_id == RuleRegistry.id)
            .where(AgentRoleRule.role_id == role.id, RuleRegistry.is_active.is_(True))
            .order_by(RuleRegistry.priority.asc(), RuleRegistry.code.asc())
        )
        exclusive_rules = (await db.execute(role_rules_stmt)).scalars().all()

        # 3. Bound Skills (Strictly filtered by AgentRoleSkill.role_id == role.id)
        role_skills_stmt = (
            select(SkillRegistry, AgentRoleSkill.auto_activate)
            .join(AgentRoleSkill, AgentRoleSkill.skill_id == SkillRegistry.id)
            .where(AgentRoleSkill.role_id == role.id, SkillRegistry.is_active.is_(True))
            .order_by(SkillRegistry.code.asc())
        )
        bound_skill_rows = (await db.execute(role_skills_stmt)).all()

        sections: List[str] = []
        if shared_rules:
            rules_txt = "\n".join([f"- **[{r.code}] {r.name}**: {r.rule_content_markdown}" for r in shared_rules])
            sections.append(f"【全公司與部門共通強制規範 (GLOBAL & DEPT RULES)】\n{rules_txt}")

        sections.append(f"【角色核心定位與職責 (ROLE SYSTEM PROMPT - {role.code})】\n{role.system_prompt}")

        if exclusive_rules:
            ex_txt = "\n".join([f"- **[{r.code}] {r.name}**: {r.rule_content_markdown}" for r in exclusive_rules])
            sections.append(f"【本角色專屬行為與格式規範 (AGENT-EXCLUSIVE RULES)】\n{ex_txt}")

        catalog_lines: List[str] = []
        active_sop_blocks: List[str] = []
        unlocked_skills: List[SkillRegistry] = []

        for skill_obj, auto_activate in bound_skill_rows:
            is_active_now = auto_activate or (skill_obj.code in activated_skill_codes)
            status_tag = "已啟用 (ACTIVE)" if is_active_now else "待命 (呼叫 activate_skill 載入)"
            catalog_lines.append(f"- `{skill_obj.code}` ({skill_obj.name}) [{status_tag}]: {skill_obj.trigger_description}")

            if is_active_now:
                unlocked_skills.append(skill_obj)
                cli_hint = ""
                if skill_obj.execution_mode in ("SERVER_SANDBOX_CLI", "LOCAL_DAEMON_CLI"):
                    schema_str = str((skill_obj.cli_config or {}).get("allowed_args_schema", {}))
                    cli_hint = (
                        f"\n  - **專屬 CLI 執行方式**: 於 `tool_calls` 呼叫 `execute_skill_cli`，"
                        f"傳入 `{{\"skill_code\": \"{skill_obj.code}\", \"cli_args\": ...}}` (參數須符合 `{schema_str}`)。"
                    )
                active_sop_blocks.append(f"### 啟用技能 SOP：`{skill_obj.code}` ({skill_obj.name})\n{skill_obj.sop_markdown}{cli_hint}")

        if catalog_lines:
            sections.append(
                "【本角色可用技能清單 (BOUND SKILLS CATALOG)】\n"
                "若任務需使用某項『待命』技能，請先在 tool_calls 呼叫 `activate_skill` 並傳入 `{\"skill_code\": \"...\"}`：\n"
                + "\n".join(catalog_lines)
            )
        if active_sop_blocks:
            sections.append("【當前已掛載之技能標準作業程序 (ACTIVE SKILL SOPs)】\n" + "\n\n".join(active_sop_blocks))

        return CompiledRoleContext(system_prompt="\n\n---\n\n".join(sections), active_skills=unlocked_skills)
~~~

---

### 6.3 Core Engine 3: Web-to-Local File System Reverse RPC Bridge (`MOD-LOCAL-FS`, `MOD-WS-RPC`)

#### `apps/web-portal/src/lib/localFsBridge.ts`
~~~typescript
// Implements: REQ-004, REQ-012 (Chromium File System Access API + IndexedDB + Path Denylist)
import { get as idbGet, set as idbSet } from 'idb-keyval';

const FORBIDDEN_PATTERNS = [/^\.env/i, /\.pem$/i, /\.pfx$/i, /^id_rsa/i, /^\.git\//i, /node_modules\//i];

export interface LocalFileEntry {
  path: string;
  size: number;
  lastModified: number;
}

export class BrowserLocalFsBridge {
  static async authorizeAndMountDirectory(): Promise<{
    handleKey: string;
    folderName: string;
    fileTree: LocalFileEntry[];
  }> {
    if (!('showDirectoryPicker' in window)) {
      throw new Error('請使用 Chrome 或 Microsoft Edge 瀏覽器以支援原生本機資料夾掛載。');
    }
    const dirHandle: FileSystemDirectoryHandle = await (window as any).showDirectoryPicker({ mode: 'readwrite' });
    const handleKey = `local_mount_${crypto.randomUUID()}`;
    await idbSet(handleKey, dirHandle);
    const fileTree = await this.scanDirectoryTree(dirHandle, '');
    return { handleKey, folderName: dirHandle.name, fileTree };
  }

  static async ensurePermission(handleKey: string, mode: 'read' | 'readwrite' = 'read'): Promise<FileSystemDirectoryHandle> {
    const dirHandle = await idbGet<FileSystemDirectoryHandle>(handleKey);
    if (!dirHandle) throw new Error('找不到本機資料夾授權紀錄，請重新綁定。');
    const opts = { mode };
    if ((await (dirHandle as any).queryPermission(opts)) === 'granted') return dirHandle;
    if ((await (dirHandle as any).requestPermission(opts)) === 'granted') return dirHandle;
    throw new Error('使用者拒絕授予本機資料夾存取權限。');
  }

  static async scanDirectoryTree(dirHandle: FileSystemDirectoryHandle, prefix: string, maxFiles = 500): Promise<LocalFileEntry[]> {
    const results: LocalFileEntry[] = [];
    for await (const [name, handle] of (dirHandle as any).entries()) {
      const relPath = prefix ? `${prefix}/${name}` : name;
      if (FORBIDDEN_PATTERNS.some((regex) => regex.test(relPath) || regex.test(name))) continue;
      if (handle.kind === 'file') {
        const file: File = await (handle as FileSystemFileHandle).getFile();
        results.push({ path: relPath, size: file.size, lastModified: file.lastModified });
        if (results.length >= maxFiles) break;
      } else if (handle.kind === 'directory') {
        const sub = await this.scanDirectoryTree(handle as FileSystemDirectoryHandle, relPath, maxFiles - results.length);
        results.push(...sub);
      }
    }
    return results;
  }

  static async readFileForAgent(handleKey: string, relativePath: string): Promise<{
    encoding: 'utf-8' | 'base64';
    mimeType: string;
    content: string;
    size: number;
  }> {
    if (relativePath.includes('..') || FORBIDDEN_PATTERNS.some((r) => r.test(relativePath))) {
      throw new Error(`Security Violation: 禁止讀取敏感或越權路徑 (${relativePath})`);
    }
    const rootHandle = await this.ensurePermission(handleKey, 'read');
    const fileHandle = await this.resolveFileHandle(rootHandle, relativePath, false);
    const file = await fileHandle.getFile();

    if (/\.(docx|xlsx|pdf|pptx)$/i.test(relativePath)) {
      const buffer = await file.arrayBuffer();
      const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)));
      return { encoding: 'base64', mimeType: file.type || 'application/octet-stream', content: base64, size: file.size };
    }
    return { encoding: 'utf-8', mimeType: 'text/plain', content: await file.text(), size: file.size };
  }

  static async commitConfirmedWrite(handleKey: string, relativePath: string, newContent: string): Promise<void> {
    if (relativePath.includes('..') || FORBIDDEN_PATTERNS.some((r) => r.test(relativePath))) {
      throw new Error(`Security Violation: 禁止寫入敏感路徑 (${relativePath})`);
    }
    const rootHandle = await this.ensurePermission(handleKey, 'readwrite');
    const fileHandle = await this.resolveFileHandle(rootHandle, relativePath, true);
    const writable = await (fileHandle as any).createWritable();
    await writable.write(newContent);
    await writable.close();
  }

  private static async resolveFileHandle(root: FileSystemDirectoryHandle, relPath: string, create: boolean): Promise<FileSystemFileHandle> {
    const parts = relPath.split('/').filter(Boolean);
    let currentDir = root;
    for (let i = 0; i < parts.length - 1; i++) {
      currentDir = await currentDir.getDirectoryHandle(parts[i], { create });
    }
    return await currentDir.getFileHandle(parts[parts.length - 1], { create });
  }
}
~~~

#### `apps/api-server/app/tool_bus/ws_rpc_manager.py`
~~~python
# Implements: REQ-004, REQ-012 (Server-to-Browser Reverse RPC Manager with Cross-User Isolation)
import asyncio
import uuid
from typing import Dict, Any, Tuple
from fastapi import WebSocket

class WebSocketReverseRPCManager:
    def __init__(self) -> None:
        self._connections: Dict[Tuple[str, str], WebSocket] = {}
        self._pending_rpcs: Dict[str, asyncio.Future] = {}

    async def register_connection(self, user_id: str, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[(user_id, session_id)] = websocket

    def unregister_connection(self, user_id: str, session_id: str) -> None:
        self._connections.pop((user_id, session_id), None)

    async def call_browser_tool(
        self,
        requester_user_id: str,
        mount_owner_user_id: str,
        session_id: str,
        method: str,
        params: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        if requester_user_id != mount_owner_user_id:
            raise PermissionError("ERR_LOCAL_MOUNT_MUST_BE_PRIVATE: 禁止跨使用者存取本機掛載目錄")

        ws = self._connections.get((requester_user_id, session_id))
        if not ws:
            return {
                "status": "BROWSER_OFFLINE",
                "error": "使用者的瀏覽器分頁未連線，請開啟平台網頁以授權存取本機資料夾。",
            }

        rpc_id = f"rpc_{uuid.uuid4().hex}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_rpcs[rpc_id] = future

        try:
            await ws.send_json({"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params})
            result = await asyncio.wait_for(future, timeout=timeout)
            return {"status": "SUCCESS", "data": result}
        except asyncio.TimeoutError:
            return {"status": "TIMEOUT", "error": f"瀏覽器本機檔案操作逾時 ({timeout}s)"}
        finally:
            self._pending_rpcs.pop(rpc_id, None)

    def resolve_rpc_response(self, rpc_id: str, payload: Dict[str, Any]) -> None:
        future = self._pending_rpcs.get(rpc_id)
        if future and not future.done():
            future.set_result(payload)

ws_rpc_manager = WebSocketReverseRPCManager()
~~~

---

### 6.4 Core Engine 4: Dual-Target Parameterized CLI Execution Engine (`MOD-CLI-EXEC`)

#### `apps/api-server/app/tool_bus/cli_executor.py`
~~~python
# Implements: REQ-015, REQ-016 (Parameterized shlex Anti-Injection & Dual-Target CLI Router)
import shlex
import time
from typing import Dict, Any, Optional
from jsonschema import validate as validate_json_schema, ValidationError
from app.db.models import SkillRegistry
from app.tool_bus.sandbox_runner import ServerDockerSandboxRunner
from app.tool_bus.ws_rpc_manager import ws_rpc_manager

FORBIDDEN_CLI_TOKENS = [
    "rm -rf /", "mkfs", "shutdown", "reboot", "init 0", "dd if=",
    ":(){ :|:& };:", "chmod 777", "chown root", "/etc/shadow", "/etc/passwd"
]

class SkillCLIExecutor:
    def __init__(self, sandbox_runner: ServerDockerSandboxRunner) -> None:
        self.sandbox_runner = sandbox_runner

    @staticmethod
    def render_safe_command(skill: SkillRegistry, cli_args: Dict[str, Any]) -> str:
        cli_cfg = skill.cli_config or {}
        args_schema = cli_cfg.get("allowed_args_schema", {})
        try:
            validate_json_schema(
                instance=cli_args,
                schema={
                    "type": "object",
                    "properties": args_schema,
                    "required": list(args_schema.keys()),
                    "additionalProperties": False,
                },
            )
        except ValidationError as e:
            raise ValueError(f"CLI 參數未通過安全 Schema 驗證: {e.message}")

        template: str = cli_cfg.get("command_template", "")
        rendered = template
        for key, val in cli_args.items():
            safe_val = shlex.quote(str(val))
            rendered = rendered.replace(f"{{{{{key}}}}}", safe_val)

        if "{{" in rendered or "}}" in rendered:
            raise ValueError("CLI 指令範本尚有未替換的參數佔位符")

        lower_cmd = rendered.lower()
        for token in FORBIDDEN_CLI_TOKENS:
            if token in lower_cmd:
                raise PermissionError(f"Security Violation: 偵測到禁止執行的危險指令片段 ({token})")

        return rendered

    async def execute(
        self,
        session_id: str,
        user_id: str,
        role_code: str,
        skill: SkillRegistry,
        cli_args: Dict[str, Any],
        browser_mount_handle_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        rendered_cmd = self.render_safe_command(skill, cli_args)
        cli_cfg = skill.cli_config or {}
        timeout = float(cli_cfg.get("timeout_seconds", 30))
        start_ts = time.monotonic()

        if skill.execution_mode == "SERVER_SANDBOX_CLI":
            synced_files: Dict[str, bytes] = {}
            if cli_cfg.get("sync_local_files") and browser_mount_handle_key and "target_file" in cli_args:
                ws_res = await ws_rpc_manager.call_browser_tool(
                    requester_user_id=user_id,
                    mount_owner_user_id=user_id,
                    session_id=session_id,
                    method="CLIENT_FS_READ",
                    params={"browser_handle_key": browser_mount_handle_key, "file_path": cli_args["target_file"]},
                )
                if ws_res.get("status") == "SUCCESS":
                    synced_files[cli_args["target_file"]] = ws_res["data"]["content"].encode("utf-8")

            res = await self.sandbox_runner.run_ephemeral_command(
                image=cli_cfg.get("sandbox_image", "enterprise-sandbox:py312-node22"),
                command=rendered_cmd,
                injected_files=synced_files,
                timeout=timeout,
            )
            return {
                "execution_target": "SERVER_SANDBOX_CLI",
                "command": rendered_cmd,
                "exit_code": res["exit_code"],
                "stdout": res["stdout"][:8000],
                "stderr": res["stderr"][:4000],
                "duration_ms": int((time.monotonic() - start_ts) * 1000),
            }

        elif skill.execution_mode == "LOCAL_DAEMON_CLI":
            ws_res = await ws_rpc_manager.call_browser_tool(
                requester_user_id=user_id,
                mount_owner_user_id=user_id,
                session_id=session_id,
                method="DAEMON_EXEC_CLI",
                params={"command": rendered_cmd, "timeout": timeout},
                timeout=timeout + 5.0,
            )
            duration_ms = int((time.monotonic() - start_ts) * 1000)
            if ws_res.get("status") != "SUCCESS":
                return {
                    "execution_target": "LOCAL_DAEMON_CLI",
                    "command": rendered_cmd,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": ws_res.get("error", "本機 Local MCP Daemon 未啟動。"),
                    "duration_ms": duration_ms,
                }
            data = ws_res["data"]
            return {
                "execution_target": "LOCAL_DAEMON_CLI",
                "command": rendered_cmd,
                "exit_code": data.get("exit_code", 0),
                "stdout": data.get("stdout", "")[:8000],
                "stderr": data.get("stderr", "")[:4000],
                "duration_ms": duration_ms,
            }

        raise ValueError(f"不支援的 CLI 執行模式: {skill.execution_mode}")
~~~

---

## 7. Built-in Roles, Rules & Skills Seed Specifications (`packages/builtin-*`)

- **`packages/builtin-roles/seed_roles.yaml`**: Seed the 7 core roles (`ORCH`, `CEO`, `PM`, `FIN`, `SA`, `ARCH`, `SE`) using the exact Traditional Chinese system prompts, Hard Negative Constraints, and Few-Shot JSON anchors provided in the Role Registry Specification.
- **`packages/builtin-skills-rules/seed_rules.yaml`**:
  - `RULE_GLOBAL_ZH_TW` (`GLOBAL_MANDATORY`, priority 10): Enforce Traditional Chinese (`zh-TW`) and Taiwanese IT terminology (`專案`, `資料庫`, `非同步`, `伺服器`, `權杖`).
  - `RULE_GLOBAL_ZERO_TRUST_DLP` (`GLOBAL_MANDATORY`, priority 20): Never leak secrets, tokens, or PII; always cite source filenames/emails.
  - `RULE_SA_OPENAPI_AND_ERD` (`ROLE_EXCLUSIVE` bound ONLY to `SA`): Snake_case plural table names, standard audit columns, OpenAPI 3.1 error schema.
  - `RULE_FIN_TWD_THREE_SCENARIOS` (`ROLE_EXCLUSIVE` bound ONLY to `FIN`): TWD (`NT$`) currency default, 36-month straight-line hardware depreciation, 3-scenario (Conservative/Base/Optimistic) ROI table.
  - `RULE_SE_PYTHON_TS_STRICT` (`ROLE_EXCLUSIVE` bound ONLY to `SE`): 100% Python 3.12 Type Hints, SQLAlchemy 2.0 AsyncSession, zero `# TODO` stubs.
- **`packages/builtin-skills-rules/seed_skills.yaml`**:
  - `SKILL_COMMON_MEETING_ACTION_ITEMS` (`PROMPT_ONLY`, bound to `PM`, `SA`, `ARCH`, `CEO`).
  - `SKILL_SA_OPENAPI_CLI_VALIDATOR` (`SERVER_SANDBOX_CLI`, `READ` tier, bound to `SA`, `ARCH`): Runs `python3 /opt/skill-scripts/validate_openapi.py --file {{target_file}}` with automatic browser local file sync.
  - `SKILL_FIN_PYTHON_IRR_CALCULATOR` (`SERVER_SANDBOX_CLI`, `READ` tier, bound to `FIN`): Runs `python3 /opt/skill-scripts/fin_calculator.py` for exact NPV/IRR/Payback math.
  - `SKILL_SE_PYTEST_AND_GIT_DIAGNOSTICS` (`LOCAL_DAEMON_CLI`, `READ` tier, bound to `SE`): Runs `pytest {{test_target}} -q --tb=short`.

---

## 8. Unified Tool & Connector Permission Matrix (`MOD-MCP-GW`, `MOD-HITL`)

| Namespace | Tool / Skill Action | Tier | Target | HITL Gate Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `local_fs` | `workspace_list_files`, `workspace_read_file` | `READ` | `BROWSER_WS_RPC` | Auto-executes; `.docx/.xlsx/.pdf` parsed via `MarkItDown` & chunked if >3,000 tokens. |
| `local_fs` | `workspace_write_file` | `COMMIT` | `BROWSER_WS_RPC` | **Pauses LangGraph (`WAITING_HITL`)**; shows Red/Green Diff in Web UI before writing disk. |
| `skill_cli` | `execute_skill_cli` (`action_tier == READ`) | `READ` | `SERVER_SANDBOX_CLI` / `LOCAL_DAEMON_CLI` | Auto-executes after `shlex.quote` & JSON schema validation; streams ANSI stdout to UI. |
| `skill_cli` | `execute_skill_cli` (`action_tier == COMMIT`) | `COMMIT` | `SERVER_SANDBOX_CLI` / `LOCAL_DAEMON_CLI` | **Pauses LangGraph (`WAITING_HITL`)**; previews rendered command for user click approval. |
| `o365_mail` | `o365_search_messages` | `READ` | `SERVER_MCP` | Auto-executes via MS Graph API using user's decrypted OBO token. |
| `o365_mail` | `o365_create_draft` | `DRAFT` | `SERVER_MCP` | Auto-executes; saves draft inside user's Outlook Drafts folder. |
| `o365_mail` | `o365_send_mail`, `o365_create_event` | `COMMIT` | `SERVER_MCP` | **Pauses LangGraph (`WAITING_HITL`)**; previews email/invite in Web & Teams Adaptive Card. |
| `teams` / `slack` | `teams_read_channel_thread`, `slack_search_messages` | `READ` | `SERVER_MCP` | Auto-executes within user-authorized channels. |
| `teams` / `slack` | `teams_send_message`, `slack_post_message` | `COMMIT` | `SERVER_MCP` | **Pauses LangGraph (`WAITING_HITL`)**; requires explicit user confirmation before posting. |

---

## 9. Complete REST, SSE & WebSocket API Contract

| Method & Path | Module | Description |
| :--- | :--- | :--- |
| `POST /api/v1/chat/sessions/{session_id}/stream` | `v1_chat.py` | SSE stream emitting `orchestrator_plan`, `role_switched`, `skill_activated`, `cli_output`, `artifact_created`, `hitl_required`, and `final_response`. |
| `POST /api/v1/agents/generate-spec` | `v1_agents.py` | Uses Gemma 4 to turn a 1-sentence description into a full Role prompt, routing description, and recommended Rule/Skill bindings. |
| `POST /api/v1/agents` | `v1_agents.py` | Creates custom agent (`PRIVATE`, `DEPARTMENT`, `GLOBAL`); enforces `ERR_LOCAL_MOUNT_MUST_BE_PRIVATE` if `bound_local_mount_id != null`. |
| `GET / POST /api/v1/rules` & `/api/v1/skills` | `v1_rules_skills.py` | CRUD for Rules & Skills and M:N binding (`agent_role_rules`, `agent_role_skills`). |
| `POST /api/v1/mounts/register` | `v1_agents.py` | Registers a browser `FileSystemDirectoryHandle` key and initial file tree metadata. |
| `POST /api/v1/hitl/{request_id}/decide` | `v1_hitl.py` | Accepts `APPROVED`, `MODIFIED` (with edited payload), or `REJECTED` and resumes the paused LangGraph checkpoint. |
| `WS /api/v1/ws/client-tools/{session_id}` | `ws_client_tools.py` | Bidirectional JSON-RPC 2.0 WebSocket channel for `CLIENT_FS_READ`, `CLIENT_FS_WRITE`, and `DAEMON_EXEC_CLI`. |

---

## 10. Step-by-Step Implementation Playbook with Gemini 4 Argon Thinking Level Tags

Execute the following 5 Milestones in order. Adjust `gemini-4-argon`'s `thinking_level` (`MEDIUM` vs. `HIGH`) per task as marked below:

### Milestone 1: Foundation, 13-Table DB Schema & Gemma 4 DAG Orchestrator
- **`M1-T1` `[建議思考等級: MEDIUM]` (`max_output_tokens: 65536`)** — **Monorepo & Database Models**:
  - Scaffold directory tree, `docker-compose.yml` (`pgvector/pgvector:pg16`, `redis:7-alpine`), `app/core/config.py`, `app/db/models.py` (all 13 tables in exact FK order from Section 5), and Alembic migration `0001_unified_schema.py`.
- **`M1-T2` `[建議思考等級: MEDIUM]` (`max_output_tokens: 65536`)** — **LLM Clients & Seed Runner**:
  - Implement `gemma_client.py` (SGLang FSM JSON Schema client), `embedding_client.py` (`google/embeddinggemma-2`), and `seed_runner.py` to load `seed_roles.yaml`, `seed_rules.yaml`, and `seed_skills.yaml`.
- **`M1-T3` `[建議思考等級: HIGH]` (`max_output_tokens: 131072`)** — **LangGraph DAG Supervisor, Claim-Check Artifact Manager & Circuit Breaker**:
  - Implement `state.py`, `artifact_manager.py`, `role_runner.py`, and `supervisor_graph.py`. Must support topological execution of `dag_steps`, `AsyncPostgresSaver` checkpointing, Claim-Check 200-word pointer passing, and hard stop at `max_hops = 8`.
- **Milestone 1 Acceptance Tests (`[建議思考等級: MEDIUM]`)**:
  - `TC-M1-01`: Verify all 7 roles, 5 rules, and 4 skills seed cleanly with 768-d embeddings.
  - `TC-M1-02`: Run multi-role prompt (`SA` -> `ARCH` + `FIN` -> `PM`), verify DAG order, verify `shared_artifacts` storage, and verify `hop_count <= 8`.
  - `TC-M1-03`: Verify 100% valid JSON output across 50 consecutive Gemma 4 SGLang calls.

### Milestone 2: Unified Tool Bus, Enterprise MCP Connectors & HITL Gate
- **`M2-T1` `[建議思考等級: HIGH]` (`max_output_tokens: 131072`)** — **AES-256-GCM Token Vault & HITL Checkpoint Interceptor**:
  - Implement `crypto_vault.py`, `hitl_interceptor.py` (LangGraph `NodeInterrupt` on `COMMIT` tier tools/CLI), and `v1_hitl.py` resume endpoint (`APPROVED` / `MODIFIED` / `REJECTED`).
- **`M2-T2` `[建議思考等級: MEDIUM]` (`max_output_tokens: 65536`)** — **Enterprise MCP Servers & Dynamic Tool RAG**:
  - Implement `mcp_o365` (MS Graph OBO Mail/Calendar/OneDrive), `mcp_teams`, `mcp_slack`, `mcp_email_generic`, and `tool_rag.py` (Top-K role/tool vector retrieval).
- **Milestone 2 Acceptance Tests (`[建議思考等級: MEDIUM]`)**:
  - `TC-M2-01`: Verify `READ` and `DRAFT` tools execute without pausing.
  - `TC-M2-02`: Verify `COMMIT` tools (`o365_send_mail`, `teams_send_message`) halt execution in `WAITING_HITL` and resume accurately with `user_modified_payload`.
  - `TC-M2-03`: Verify `tool_rag.py` caps injected tools at Top-5 per role turn.

### Milestone 3: Web Portal PWA, Self-Service Agent Studio & Browser Local File Bridge
- **`M3-T1` `[建議思考等級: HIGH]` (`max_output_tokens: 131072`)** — **WebSocket Reverse RPC & Stateless Document Parser**:
  - Implement backend `ws_rpc_manager.py`, `ws_client_tools.py`, `doc_parser.py` (`MarkItDown` + >3,000 token ephemeral chunking), and frontend `localFsBridge.ts` + `wsClientToolRunner.ts`.
- **`M3-T2` `[建議思考等級: MEDIUM]` (`max_output_tokens: 65536`)** — **Next.js 15 Workspace, Org Chart & Custom Agent Studio**:
  - Implement `/chat` (split-screen with `ArtifactViewer`, `LocalFileDiffModal`, `HitlApprovalCard`), `/org-chart` (React Flow live DAG & Kanban), and `/studio` (`AgentMetaWizard` + local mount binder).
- **Milestone 3 Acceptance Tests (`[建議思考等級: MEDIUM]`)**:
  - `TC-M3-01`: Create custom agent via 1-sentence Meta-Prompt; verify binding a local mount enforces `visibility_scope = 'PRIVATE'`.
  - `TC-M3-02`: Mount local directory in browser, read `.docx` via Reverse RPC, and confirm writing `api_spec.md` requires clicking confirm in `LocalFileDiffModal`.
  - `TC-M3-03`: Verify path traversal (`../`) and `.env`/`.pem` reads are rejected on both client and server.

### Milestone 4: 24/7 Background Heartbeats, Optional Local Daemon & Zero-Trust Audit
- **`M4-T1` `[建議思考等級: MEDIUM]` (`max_output_tokens: 65536`)** — **Celery 24/7 Heartbeat Workers & Optional Local Daemon**:
  - Implement `celery_app.py`, `ticket_worker.py` (`SELECT ... FOR UPDATE SKIP LOCKED` atomic checkout), `heartbeat_cron.py`, and `packages/local-mcp-daemon/daemon.py`.
- **`M4-T2` `[建議思考等級: HIGH]` (`max_output_tokens: 131072`)** — **Multi-Tenant / Cross-User Zero-Trust Penetration Audit**:
  - Audit all queries in `v1_chat.py`, `v1_agents.py`, `ws_rpc_manager.py`, and `memory_search` to guarantee zero cross-user leakage of `PRIVATE` agents, OBO tokens, or browser mounts.
- **Milestone 4 Acceptance Tests (`[建議思考等級: MEDIUM]`)**:
  - `TC-M4-01`: Verify background cron executes server MCP tools while browser is closed and gracefully notifies user if a local browser mount is offline.
  - `TC-M4-02`: Verify `LOCAL_MCP_DAEMON` seamlessly handles `workspace_*` calls when browser tab is closed.
  - `TC-M4-03`: Pass cross-user unauthorized access penetration test suite (`0` leaks).

### Milestone 5: Role-Isolated Rules, Progressive Skills & Dual-Target CLI Sandbox
- **`M5-T1` `[建議思考等級: HIGH]` (`max_output_tokens: 131072`)** — **Onion Prompt Compiler, Parameterized CLI Executor & Rootless Docker Sandbox**:
  - Implement `prompt_compiler.py`, `cli_executor.py` (`shlex.quote` + JSON Schema validation + denylist), `sandbox_runner.py` (ephemeral rootless container with `network_mode="none"`, `mem_limit="512m"`, `pids_limit=64`, read-only rootfs), and bundled scripts (`validate_openapi.py`, `fin_calculator.py`).
- **`M5-T2` `[建議思考等級: MEDIUM]` (`max_output_tokens: 65536`)** — **Frontend Rule/Skill Studio & Live ANSI Terminal Card**:
  - Implement `v1_rules_skills.py`, `RuleBindingSelector.tsx`, `SkillEditorModal.tsx`, and `TerminalOutputCard.tsx`.
- **Milestone 5 Acceptance Tests (`[建議思考等級: MEDIUM]`)**:
  - `TC-M5-01`: Verify `SA` prompt contains `RULE_GLOBAL_ZH_TW` + `RULE_SA_OPENAPI_AND_ERD` and **0%** of `FIN` or `SE` exclusive rules.
  - `TC-M5-02`: Verify Stage-1 skill catalog uses <60 tokens per skill and Stage-2 SOP loads only after `activate_skill` is called.
  - `TC-M5-03`: Verify pure Web execution of `SKILL_SA_OPENAPI_CLI_VALIDATOR` and `SKILL_FIN_PYTHON_IRR_CALCULATOR` inside `SERVER_SANDBOX_CLI` with automatic browser file sync.
  - `TC-M5-04`: Verify CLI command injection (`; rm -rf /`) is blocked by `render_safe_command` and `COMMIT`-tier CLI skills pause for HITL approval.
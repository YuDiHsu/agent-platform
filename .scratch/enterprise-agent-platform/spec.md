# Enterprise Multi-Agent Platform (`enterprise-agent-platform`)

**Status:** ready-for-agent

## Canonical Specification

- **Master Specification (Read-Only Source of Truth)**: [`MASTER_SPEC.md`](../../MASTER_SPEC.md) (`EAMP-MASTER-SPEC-2026-V3.0`)
- **Frontend UI/UX & Interactive State Specification**: [`UI_SPEC.md`](../../UI_SPEC.md) (`EAMP-UI-SPEC-2026-V3.0`)
- **Product & Accessibility Context**: [`PRODUCT.md`](../../PRODUCT.md)
- **Architecture Decision Overrides (`docs/adr/`)**:
  - [`0001-configurable-embedding-model-and-dimension.md`](../../docs/adr/0001-configurable-embedding-model-and-dimension.md) — Overrides `MASTER_SPEC.md`'s hardcoded `google/embeddinggemma-2 (768-d)` with a config-driven OpenAI-compatible Embedding client and configurable `EMBEDDING_DIMENSION` (supporting `BAAI/bge-m3` et al.).
- **Built-in Role Seed Reference**: [`packages/builtin-roles/seed_roles.yaml`](../../packages/builtin-roles/seed_roles.yaml)
- **Legacy Layer Checklist**: [`TASKS.md`](../../TASKS.md)

## Ticket Task Graph (`.scratch/enterprise-agent-platform/issues/`)

1. [`01-platform-skeleton-schema-and-seed.md`](./issues/01-platform-skeleton-schema-and-seed.md) — **Blocked by:** None
2. [`02-multi-role-dag-claim-check-and-chat-workspace.md`](./issues/02-multi-role-dag-claim-check-and-chat-workspace.md) — **Blocked by:** `01`
3. [`03-onion-prompt-compiler-and-progressive-skills.md`](./issues/03-onion-prompt-compiler-and-progressive-skills.md) — **Blocked by:** `01`, `02`
4. [`04-token-vault-and-dynamic-tool-rag.md`](./issues/04-token-vault-and-dynamic-tool-rag.md) — **Blocked by:** `01`
5. [`05-hitl-security-gate-and-checkpoint-resume.md`](./issues/05-hitl-security-gate-and-checkpoint-resume.md) — **Blocked by:** `02`
6. [`06-enterprise-mcp-connectors-and-tool-bus.md`](./issues/06-enterprise-mcp-connectors-and-tool-bus.md) — **Blocked by:** `04`, `05`
7. [`07-browser-local-fs-reverse-rpc-and-diff-write.md`](./issues/07-browser-local-fs-reverse-rpc-and-diff-write.md) — **Blocked by:** `02`, `05`
8. [`08-self-service-agent-studio-and-mount-privacy.md`](./issues/08-self-service-agent-studio-and-mount-privacy.md) — **Blocked by:** `02`, `07`
9. [`09-parameterized-cli-sandbox-and-terminal-card.md`](./issues/09-parameterized-cli-sandbox-and-terminal-card.md) — **Blocked by:** `03`, `05`, `07`
10. [`10-background-heartbeats-atomic-worker-and-local-daemon.md`](./issues/10-background-heartbeats-atomic-worker-and-local-daemon.md) — **Blocked by:** `06`, `07`, `09`
11. [`11-zero-trust-security-audit-and-full-regression.md`](./issues/11-zero-trust-security-audit-and-full-regression.md) — **Blocked by:** `08`, `10`

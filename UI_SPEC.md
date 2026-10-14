# Enterprise Multi-Agent Platform - Frontend UI/UX & Interactive State Specification (`UI_SPEC.md`)

- **Document ID**: `EAMP-UI-SPEC-2026-V3.0`
- **Companion To**: `MASTER_SPEC.md` & `TASKS.md` (`TASK-16`, `TASK-17`, `TASK-18`, `TASK-27`)
- **Framework**: Next.js 15 (App Router, TypeScript Strict), React 19, TailwindCSS, Shadcn UI, Zustand, `@xyflow/react`, `mermaid`, `react-diff-viewer-continued`, `lucide-react`

---

## 1. Global Application Shell & 3-Pane Responsive Layout

All pages under `apps/web-portal/src/app/` share a unified enterprise dark/light adaptive shell (`AppShell.tsx`):

~~~text
+----------------------------------------------------------------------------------------------------------+
| Top Header Bar (h-14):                                                                                   |
| [Logo: Enterprise Agent Hub] | [Active Session Title]          [Local Mount: 🟢 2 Connected] [HITL 🔔(1)] |
+-------+---------------------------------------------+----------------------------------------------------+
| Left  | Center Primary Stage (flex-1, min-w-[480px])| Right Context & Artifact Workbench (w-[45%],       |
| Nav   |                                             | collapsible, resizable split-pane)                 |
| Rail  | [Mini Live DAG Progress Bar:                | +------------------------------------------------+ |
| (w-64)|  ✅ SA (Spec) ──> 🔵 ARCH (Diagram) ──> ⚪ PM]| | Tabs: [📄 Artifact] [🔀 Diff(1)] [💻 CLI] [🕸️ DAG]| |
|       | ------------------------------------------- | +------------------------------------------------+ |
| [💬]  | Multi-Agent Chat Stream:                    | |                                                | |
| 協作區 |                                             | |  Live Rendered Preview Area:                   | |
|       | 👤 User: 請讀取本機訪談紀錄並設計架構...     | |  - Markdown Table / PRD Viewer                 | |
| [🏢]  |                                             | |  - Interactive Mermaid Flowchart / Sequence    | |
| 組織圖 | 🤖 [ORCH 主代理]: 已拆解 3 步工單...         | |  - Side-by-Side Red/Green Local File Diff      | |
| 與看板 |                                             | |  - ANSI Dark Terminal Output (`exit_code: 0`)  | |
|       | 🧑‍💻 [SA 系統分析師] (Used Skill: OpenAPI):   | |                                                | |
| [📦]  |    已讀取 `訪談紀錄.docx`，產出功能規格 👉   | |                                                | |
| 產出物 |    [📄 點擊於右側開啟 SRS 規格書 v1]         | |                                                | |
| 中心  |                                             | |                                                | |
|       | 🛡️ [HITL 安全審批攔截卡片 - WAITING_HITL]:  | +------------------------------------------------+ |
| [🛠️]  |    PM 請求執行 `o365_send_mail`             | | Action Footer:                                 | |
| 自建  |    收件人: dev-team@company.com             | | [⬇️ 下載 .md] [💾 寫入本機資料夾] [✏️ 編輯內容] | |
| 工作坊 |    [✅ 核准發送] [✏️ 右側修改後發送] [❌ 拒絕]| +------------------------------------------------+ |
|       | ------------------------------------------- |                                                    |
| [⚙️]  | Bottom Composer:                            |                                                    |
| 連接器 | [📁 掛載本機目錄: 客戶A規格 ▼] [@ 指定角色]  |                                                    |
| 與排程 | [ 輸入指令... (Shift+Enter 換行)      [發送]]|                                                    |
+-------+---------------------------------------------+----------------------------------------------------+
~~~

---

## 2. Frontend Global State Store & SSE Event Binding (`src/lib/store/useWorkspaceStore.ts`)

Coding Agents MUST implement this exact Zustand store so that backend Server-Sent Events (`/api/v1/chat/sessions/{id}/stream`) automatically drive the UI panels without manual page refreshes:

~~~typescript
// Target Path: apps/web-portal/src/lib/store/useWorkspaceStore.ts
// Implements: REQ-002, REQ-004, REQ-007, REQ-010, REQ-015
import { create } from 'zustand';

export type RightPaneTab = 'ARTIFACT' | 'FILE_DIFF' | 'TERMINAL_CLI' | 'LIVE_DAG' | 'PROMPT_INSPECTOR';

export interface DAGStepUI {
  step_id: number;
  target_role_code: string;
  task_title: string;
  status: 'PENDING' | 'IN_PROGRESS' | 'WAITING_HITL' | 'COMPLETED' | 'FAILED';
  depends_on_steps: number[];
}

export interface ArtifactItemUI {
  artifact_id: string;
  producer_role: string;
  title: string;
  artifact_type: string;
  summary_200_words: string;
  content_body: string;
  created_at: string;
}

export interface HitlRequestUI {
  hitl_request_id: string;
  ticket_id: string;
  executing_role_code: string;
  tool_name: string;
  execution_target: 'SERVER_MCP' | 'BROWSER_WS_RPC' | 'SERVER_SANDBOX_CLI' | 'LOCAL_DAEMON_CLI';
  preview_title: string;
  proposed_payload: Record<string, any>;
  status: 'PENDING' | 'APPROVED' | 'MODIFIED' | 'REJECTED';
}

export interface PendingLocalWriteDiff {
  rpc_id: string;
  handleKey: string;
  relativePath: string;
  originalContent: string;
  proposedContent: string;
  executingRole: string;
}

export interface TerminalExecutionLogUI {
  id: string;
  role_code: string;
  skill_code: string;
  execution_target: 'SERVER_SANDBOX_CLI' | 'LOCAL_DAEMON_CLI';
  command: string;
  exit_code: number | null;
  stdout: string;
  stderr: string;
  duration_ms?: number;
}

interface WorkspaceState {
  sessionId: string;
  activeRoleCode: string | null;
  isRightPaneOpen: boolean;
  activeRightTab: RightPaneTab;

  // Live Multi-Agent State
  dagSteps: DAGStepUI[];
  artifacts: ArtifactItemUI[];
  selectedArtifactId: string | null;
  hitlRequests: HitlRequestUI[];
  pendingLocalDiff: PendingLocalWriteDiff | null;
  terminalLogs: TerminalExecutionLogUI[];

  // Local Mounts Status
  mountedFolders: Array<{ mountId: string; alias: string; handleKey: string; isConnected: boolean; fileCount: number }>;

  // Actions triggered by SSE or WebSocket RPC
  handleSSEEvent: (eventType: string, payload: any) => void;
  openPendingLocalDiff: (diff: PendingLocalWriteDiff) => void;
  resolvePendingLocalDiff: () => void;
  selectArtifact: (artifactId: string) => void;
  setRightTab: (tab: RightPaneTab) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  sessionId: '',
  activeRoleCode: null,
  isRightPaneOpen: true,
  activeRightTab: 'ARTIFACT',
  dagSteps: [],
  artifacts: [],
  selectedArtifactId: null,
  hitlRequests: [],
  pendingLocalDiff: null,
  terminalLogs: [],
  mountedFolders: [],

  handleSSEEvent: (eventType, payload) => {
    switch (eventType) {
      case 'orchestrator_plan':
        // Automatically populate the top Mini DAG bar & Org Chart active state
        set({ dagSteps: payload.dag_steps, isRightPaneOpen: true, activeRightTab: 'LIVE_DAG' });
        break;

      case 'role_switched':
        set((state) => ({
          activeRoleCode: payload.active_role,
          dagSteps: state.dagSteps.map((s) =>
            s.step_id === payload.step_id ? { ...s, status: 'IN_PROGRESS' } : s
          ),
        }));
        break;

      case 'artifact_created':
        // Automatically slide open the right-hand Artifact Viewer when SA/ARCH/SE finishes a deliverable
        set((state) => ({
          artifacts: [payload, ...state.artifacts],
          selectedArtifactId: payload.artifact_id,
          isRightPaneOpen: true,
          activeRightTab: 'ARTIFACT',
          dagSteps: state.dagSteps.map((s) =>
            s.step_id === payload.step_id ? { ...s, status: 'COMPLETED' } : s
          ),
        }));
        break;

      case 'cli_output':
        // Automatically switch right pane to ANSI Terminal view when a Skill executes a CLI command
        set((state) => ({
          terminalLogs: [payload, ...state.terminalLogs],
          isRightPaneOpen: true,
          activeRightTab: 'TERMINAL_CLI',
        }));
        break;

      case 'hitl_required':
        set((state) => ({
          hitlRequests: [payload, ...state.hitlRequests],
          dagSteps: state.dagSteps.map((s) =>
            s.target_role_code === payload.executing_role_code ? { ...s, status: 'WAITING_HITL' } : s
          ),
        }));
        break;
    }
  },

  openPendingLocalDiff: (diff) =>
    set({ pendingLocalDiff: diff, isRightPaneOpen: true, activeRightTab: 'FILE_DIFF' }),

  resolvePendingLocalDiff: () => set({ pendingLocalDiff: null }),

  selectArtifact: (artifactId) =>
    set({ selectedArtifactId: artifactId, isRightPaneOpen: true, activeRightTab: 'ARTIFACT' }),

  setRightTab: (tab) => set({ activeRightTab: tab, isRightPaneOpen: true }),
}));
~~~

---

## 3. Detailed Screen-by-Screen Component Specifications

### 3.1 Screen 1: Split-Screen Multi-Agent Cowork Workspace (`/chat/page.tsx` - `TASK-17`)
1. **Top Mini DAG Stepper (`MiniDagProgressBar.tsx`)**:
   - Displays horizontal pills for each step in `dagSteps` (e.g., `1. SA 需求拆解` $\rightarrow$ `2. ARCH 架構設計` $\rightarrow$ `3. FIN 財務試算` $\rightarrow$ `4. PM 通知信草擬`).
   - Color coding: `COMPLETED` (Emerald-600), `IN_PROGRESS` (Blue-600 with `animate-pulse`), `WAITING_HITL` (Amber-500 with shield alert icon), `PENDING` (Slate-400).
2. **Multi-Role Chat Stream (`ChatStream.tsx`)**:
   - Each message bubble displays a distinct **Role Identity Header** (`RoleBadge.tsx`):
     - `ORCH`: Purple badge (`主代理 Orchestrator`)
     - `SA`: Cyan badge (`系統分析師 SA`)
     - `ARCH`: Indigo badge (`架構分析師 ARCH`)
     - `SE`: Emerald badge (`資深工程師 SE`)
     - `FIN`: Amber badge (`財務專家 FIN`)
     - `PM`: Blue badge (`專案經理 PM`)
     - `CEO`: Rose badge (`執行長決策代理 CEO`)
   - **Claim-Check Artifact Card inside Chat**: Instead of dumping a 3,000-word specification inside the chat bubble, render a sleek card showing `artifact.title`, `artifact.summary_200_words`, and a button **`[📄 在右側工作區開啟完整規格與圖表]`** (`onClick={() => selectArtifact(artifact.artifact_id)}`).
3. **Inline HITL Security Approval Card (`HitlApprovalCard.tsx`)**:
   - Rendered directly in the chat stream AND in the top notification drawer whenever a `COMMIT` tier tool (`o365_send_mail`, `teams_send_message`, `execute_skill_cli`) triggers `WAITING_HITL`.
   - Displays: `executing_role_code`, `tool_name`, `execution_target` badge, and a collapsible JSON/Formatted preview of recipients, subject, and body.
   - 3 Action Buttons:
     - **`[✅ 核准執行]`** (`POST /api/v1/hitl/{id}/decide` with `status: "APPROVED"`)
     - **`[✏️ 在右側修改內容後執行]`** (Opens editable form in right pane, submits `status: "MODIFIED"` with `user_modified_payload`)
     - **`[❌ 拒絕並退回 Agent]`** (`status: "REJECTED"`)
4. **Right-Hand Multi-Tab Workbench (`ArtifactViewer.tsx`, `LocalFileDiffModal.tsx`, `TerminalOutputCard.tsx`)**:
   - **Tab 1 (`ARTIFACT`)**: Renders Markdown tables, code blocks with copy button, and automatically detects ```` ~~~mermaid ```` blocks to render interactive SVG zoom/pan diagrams using `mermaid.render()`. Includes buttons to **`[⬇️ 匯出 .md]`** or **`[💾 直接寫入本機掛載資料夾]`**.
   - **Tab 2 (`FILE_DIFF`)**: Powered by `react-diff-viewer-continued` (split view). When an Agent invokes `workspace_write_file` on a user's mounted local folder, this tab automatically opens comparing `originalContent` (left, red) vs. `proposedContent` (right, green). The browser ONLY writes to the physical disk after the user clicks **`[💾 確認寫入本機硬碟]`**.
   - **Tab 3 (`TERMINAL_CLI`)**: Dark-themed terminal emulator (`bg-slate-950 font-mono text-xs`) showing `[SERVER_SANDBOX_CLI]` or `[LOCAL_DAEMON_CLI]` badge, the exact `shlex`-escaped command, execution duration (`ms`), `exit_code` pill, and scrollable `stdout` / `stderr`.

### 3.2 Screen 2: Interactive Org Chart & Live Ticket Kanban (`/org-chart/page.tsx` - `TASK-18`)
1. **View Toggle**: Top segmented control switching between **`[🕸️ 代理組織拓撲圖 (Org Chart)]`** and **`[📋 工單看板與 Token 追蹤 (Ticket Kanban)]`**.
2. **React Flow Org Chart (`@xyflow/react`)**:
   - Renders hierarchy edges using `reports_to_id` (`ORCH` at root $\rightarrow$ `CEO` $\rightarrow$ `PM` $\rightarrow$ `SA`, `ARCH`, `SE`, `FIN`, plus user-created `CUSTOM_*` nodes).
   - **Custom Node Card (`AgentOrgNode.tsx`)**: Shows role avatar, name, code, visibility scope badge (`GLOBAL` / `DEPT` / `PRIVATE`), bound Rule count, bound Skill count, and current active ticket status.
   - Clicking any node opens a right-side slide-over drawer showing that role's recent tickets, token consumption (`tokens_consumed / token_budget`), and bound skills.

### 3.3 Screen 3: Self-Service Agent, Rule & Skill Studio (`/studio/page.tsx` - `TASK-18` & `TASK-27`)
1. **Left Pane — 4-Step Visual Builder (`AgentMetaWizard.tsx`)**:
   - **Step 1 (AI 一句話自動生成)**: Textarea where user types natural language (e.g., *"幫我建立一個檢查本機採購合約資料夾並標出違約罰則的法務助理"*), clicks **`[✨ 呼叫 Gemma 4 自動生成規格]`** (`POST /api/v1/agents/generate-spec`), and watches the form auto-populate.
   - **Step 2 (基本身分與發布範圍)**: Role Name, Code, Department, `reports_to_id` dropdown, and `visibility_scope` radio cards (`PRIVATE`, `DEPARTMENT`, `GLOBAL`).
     - *UI Guardrail*: When the user selects a Local Folder Mount in Step 3, the UI automatically locks `visibility_scope` to `PRIVATE` and shows a tooltip: *"🔒 為保護您的電腦檔案安全，綁定本機資料夾的 Agent 強制設為個人私有。"*
   - **Step 3 (工具連接器與本機資料夾綁定)**: Checkboxes for `o365_mail`, `o365_calendar`, `teams`, `slack`, and a selector for `bound_local_mount_id` (with an inline **`[+ 新增掛載本機資料夾]`** button that calls `BrowserLocalFsBridge.authorizeAndMountDirectory()`).
   - **Step 4 (Rule 守則與 Skill 技能包隔離綁定 - `RuleBindingSelector.tsx` & `SkillEditorModal.tsx`)**:
     - Shows locked badges for `GLOBAL_MANDATORY` rules (auto-inherited).
     - Multi-select checkboxes for `ROLE_EXCLUSIVE` rules and `Skills` (`PROMPT_ONLY`, `SERVER_SANDBOX_CLI`, `LOCAL_DAEMON_CLI`), plus a **`[+ 新增專屬 Rule / CLI Skill]`** modal.
2. **Right Pane — Live Prompt Onion Inspector & Test Sandbox**:
   - Displays a color-coded preview of the exact compiled prompt output from `PromptCompiler.compile_for_role()`:
     - 🟦 Layer 1: Global & Dept Rules (KV-Cache Shared Prefix)
     - 🟪 Layer 2: Role System Prompt
     - 🟧 Layer 3: Agent-Exclusive Rules (Isolated)
     - 🟩 Layer 4: Stage-1 Compact Skill Manifests
   - Allows the creator to send a test message right inside Studio to verify the custom agent's JSON output before saving.
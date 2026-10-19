import { diffFromHitl } from "@/lib/localWrite";
import { create } from "zustand";

export type RightPaneTab = "ARTIFACT" | "FILE_DIFF" | "TERMINAL_CLI" | "LIVE_DAG" | "PROMPT_INSPECTOR";

export type DagStatus =
  | "PENDING"
  | "IN_PROGRESS"
  | "WAITING_HITL"
  | "WAITING_BROWSER"
  | "PAUSED_QUOTA_EXCEEDED"
  | "COMPLETED"
  | "FAILED"
  | "CIRCUIT_BROKEN";

export interface DAGStepUI {
  step_id: number;
  target_role_code: string;
  task_title: string;
  status: DagStatus;
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
  execution_target: "SERVER_MCP" | "BROWSER_WS_RPC" | "SERVER_SANDBOX_CLI" | "LOCAL_DAEMON_CLI";
  preview_title: string;
  proposed_payload: Record<string, unknown>;
  status: "PENDING" | "APPROVED" | "MODIFIED" | "REJECTED";
}

export interface PendingLocalWriteDiff {
  rpc_id: string;
  hitlRequestId?: string;
  handleKey: string;
  relativePath: string;
  originalContent: string;
  proposedContent: string;
  executingRole: string;
}

export interface MountedFolder {
  mountId: string;
  alias: string;
  handleKey: string;
  isConnected: boolean;
  needsPermission: boolean;
  fileCount: number;
}

export interface TerminalExecutionLogUI {
  id: string;
  role_code: string;
  skill_code: string;
  execution_target: "SERVER_SANDBOX_CLI" | "LOCAL_DAEMON_CLI";
  command: string;
  exit_code: number | null;
  stdout: string;
  stderr: string;
  duration_ms?: number;
}

export interface ChatMessageUI {
  id: string;
  roleCode: string;
  eventType: string;
  content: string;
  payload?: Record<string, unknown>;
}

export interface SessionSnapshot {
  session_id: string;
  title: string;
  status: string;
  active_role_code: string | null;
  dag_steps: DAGStepUI[];
  artifacts: ArtifactItemUI[];
  messages: Array<{
    id: string;
    role_code: string;
    event_type: string;
    content: string;
    payload?: Record<string, unknown>;
  }>;
  pending_hitl: HitlRequestUI[];
}

interface WorkspaceState {
  sessionId: string;
  sessionTitle: string;
  activeRoleCode: string | null;
  isRightPaneOpen: boolean;
  activeRightTab: RightPaneTab;
  dagSteps: DAGStepUI[];
  artifacts: ArtifactItemUI[];
  selectedArtifactId: string | null;
  hitlRequests: HitlRequestUI[];
  hitlEditor: HitlRequestUI | null;
  beginHitlEdit: (request: HitlRequestUI) => void;
  clearHitlEditor: () => void;
  markHitlDecided: (requestId: string) => void;
  pendingLocalDiff: PendingLocalWriteDiff | null;
  terminalLogs: TerminalExecutionLogUI[];
  mountedFolders: MountedFolder[];
  messages: ChatMessageUI[];
  liveAnnouncement: string;
  handleSSEEvent: (eventType: string, payload: Record<string, unknown>) => void;
  openPendingLocalDiff: (diff: PendingLocalWriteDiff) => void;
  setPendingOriginal: (content: string) => void;
  resolvePendingLocalDiff: () => void;
  setMountedFolders: (folders: MountedFolder[]) => void;
  selectArtifact: (artifactId: string) => void;
  setRightTab: (tab: RightPaneTab) => void;
  appendMessage: (message: ChatMessageUI) => void;
  hydrate: (snapshot: SessionSnapshot) => void;
  resetConversation: () => void;
  setSessionId: (sessionId: string) => void;
}

function prependHitl(current: HitlRequestUI[], next: HitlRequestUI | null): HitlRequestUI[] {
  if (next === null) return current;
  if (current.some((item) => item.hitl_request_id === next.hitl_request_id)) return current;
  return [next, ...current];
}

function clearDecidedStep(steps: DAGStepUI[], request: HitlRequestUI | undefined): DAGStepUI[] {
  let cleared = false;
  return steps.map((step) => {
    if (
      !cleared &&
      request &&
      step.status === "WAITING_HITL" &&
      step.target_role_code === request.executing_role_code
    ) {
      cleared = true;
      return { ...step, status: "COMPLETED" };
    }
    return step;
  });
}

function asSteps(value: unknown): DAGStepUI[] {
  if (!Array.isArray(value)) return [];
  return value as DAGStepUI[];
}

function asArtifact(value: Record<string, unknown>): ArtifactItemUI {
  return {
    artifact_id: String(value.artifact_id ?? ""),
    producer_role: String(value.producer_role ?? ""),
    title: String(value.title ?? ""),
    artifact_type: String(value.artifact_type ?? ""),
    summary_200_words: String(value.summary_200_words ?? ""),
    content_body: String(value.content_body ?? ""),
    created_at: String(value.created_at ?? ""),
  };
}

function asHitl(value: Record<string, unknown>): HitlRequestUI {
  return {
    hitl_request_id: String(value.hitl_request_id ?? ""),
    ticket_id: String(value.ticket_id ?? ""),
    executing_role_code: String(value.executing_role_code ?? ""),
    tool_name: String(value.tool_name ?? ""),
    execution_target: String(value.execution_target ?? "SERVER_MCP") as HitlRequestUI["execution_target"],
    preview_title: String(value.preview_title ?? ""),
    proposed_payload:
      value.proposed_payload && typeof value.proposed_payload === "object"
        ? (value.proposed_payload as Record<string, unknown>)
        : {},
    status: "PENDING",
  };
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  sessionId: "",
  sessionTitle: "新的協作",
  activeRoleCode: null,
  isRightPaneOpen: true,
  activeRightTab: "ARTIFACT",
  dagSteps: [],
  artifacts: [],
  selectedArtifactId: null,
  hitlRequests: [],
  hitlEditor: null,
  beginHitlEdit: (request) =>
    set({
      hitlEditor: request,
      isRightPaneOpen: true,
      activeRightTab: "FILE_DIFF",
    }),
  clearHitlEditor: () => set({ hitlEditor: null }),
  markHitlDecided: (requestId) =>
    set((state) => ({
      hitlRequests: state.hitlRequests.filter((item) => item.hitl_request_id !== requestId),
      hitlEditor: state.hitlEditor?.hitl_request_id === requestId ? null : state.hitlEditor,
      dagSteps: clearDecidedStep(state.dagSteps, state.hitlRequests.find((item) => item.hitl_request_id === requestId)),
    })),
  pendingLocalDiff: null,
  terminalLogs: [],
  mountedFolders: [],
  messages: [],
  liveAnnouncement: "",

  handleSSEEvent: (eventType, payload) => {
    const id = crypto.randomUUID();
    switch (eventType) {
      case "orchestrator_plan": {
        const steps = asSteps(payload.dag_steps);
        set((state) => ({
          dagSteps: steps,
          isRightPaneOpen: true,
          activeRightTab: "LIVE_DAG",
          liveAnnouncement:
            steps.length === 0 ? "主代理直接回覆，沒有拆出工單。" : `主代理已拆解 ${steps.length} 個步驟。`,
          messages: [
            ...state.messages,
            {
              id,
              roleCode: "ORCH",
              eventType,
              content: String(payload.reasoning ?? ""),
              payload,
            },
          ],
        }));
        break;
      }
      case "role_switched":
        set((state) => ({
          activeRoleCode: String(payload.active_role ?? ""),
          liveAnnouncement: `${String(payload.active_role ?? "")} 開始執行 ${String(payload.task_title ?? "")}`,
          dagSteps: state.dagSteps.map((step) =>
            step.step_id === payload.step_id ? { ...step, status: "IN_PROGRESS" } : step,
          ),
          messages: [
            ...state.messages,
            {
              id,
              roleCode: String(payload.active_role ?? ""),
              eventType,
              content: `${String(payload.active_role ?? "")} 開始執行：${String(payload.task_title ?? "")}`,
              payload,
            },
          ],
        }));
        break;
      case "artifact_created": {
        const artifact = asArtifact(payload);
        set((state) => ({
          artifacts: [artifact, ...state.artifacts],
          selectedArtifactId: artifact.artifact_id,
          isRightPaneOpen: true,
          activeRightTab: "ARTIFACT",
          liveAnnouncement: `${artifact.producer_role} 完成交付物 ${artifact.title}`,
          dagSteps: state.dagSteps.map((step) =>
            step.step_id === payload.step_id ? { ...step, status: "COMPLETED" } : step,
          ),
          messages: [
            ...state.messages,
            {
              id,
              roleCode: artifact.producer_role,
              eventType,
              content: artifact.summary_200_words,
              payload,
            },
          ],
        }));
        break;
      }
      case "cli_output":
        set((state) => ({
          terminalLogs: [payload as unknown as TerminalExecutionLogUI, ...state.terminalLogs],
          isRightPaneOpen: true,
          activeRightTab: "TERMINAL_CLI",
          liveAnnouncement: "技能執行產生終端機輸出。",
        }));
        break;
      case "hitl_required": {
        const hitl = asHitl(payload);
        set((state) => {
          const connected = state.mountedFolders.find((folder) => folder.isConnected) ?? state.mountedFolders[0];
          const diff = diffFromHitl(hitl, connected?.handleKey ?? "");
          return {
            hitlRequests: prependHitl(state.hitlRequests, hitl),
            liveAnnouncement: `${hitl.executing_role_code} 等待人工審批 ${hitl.tool_name}`,
            dagSteps: state.dagSteps.map((step) =>
              step.target_role_code === payload.executing_role_code ? { ...step, status: "WAITING_HITL" } : step,
            ),
            ...(diff
              ? { pendingLocalDiff: diff, isRightPaneOpen: true, activeRightTab: "FILE_DIFF" as const }
              : {}),
          };
        });
        break;
      }
      case "final_response":
        set((state) => ({
          liveAnnouncement: String(payload.text ?? "主代理已完成回覆。"),
          messages: [
            ...state.messages,
            {
              id,
              roleCode: "ORCH",
              eventType,
              content: String(payload.text ?? ""),
              payload,
            },
          ],
        }));
        break;
      case "checkpoint_hibernated": {
        const hitl = payload.hitl && typeof payload.hitl === "object" ? asHitl(payload.hitl as Record<string, unknown>) : null;
        const status = String(payload.status ?? "WAITING_HITL") as DagStatus;
        set((state) => ({
          liveAnnouncement: String(payload.text ?? "工作區已休眠。"),
          hitlRequests: prependHitl(state.hitlRequests, hitl),
          dagSteps: state.dagSteps.map((step) => (step.step_id === payload.step_id ? { ...step, status } : step)),
          messages: [
            ...state.messages,
            {
              id,
              roleCode: "ORCH",
              eventType,
              content: String(payload.text ?? ""),
              payload,
            },
          ],
        }));
        break;
      }
      default:
        break;
    }
  },

  openPendingLocalDiff: (diff) => set({ pendingLocalDiff: diff, isRightPaneOpen: true, activeRightTab: "FILE_DIFF" }),
  setPendingOriginal: (content) =>
    set((state) =>
      state.pendingLocalDiff
        ? { pendingLocalDiff: { ...state.pendingLocalDiff, originalContent: content } }
        : {},
    ),
  resolvePendingLocalDiff: () => set({ pendingLocalDiff: null }),
  setMountedFolders: (folders) => set({ mountedFolders: folders }),
  selectArtifact: (artifactId) => set({ selectedArtifactId: artifactId, isRightPaneOpen: true, activeRightTab: "ARTIFACT" }),
  setRightTab: (tab) => set({ activeRightTab: tab, isRightPaneOpen: true }),
  appendMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  hydrate: (snapshot) =>
    set({
      sessionId: snapshot.session_id,
      sessionTitle: snapshot.title,
      activeRoleCode: snapshot.active_role_code,
      dagSteps: snapshot.dag_steps,
      artifacts: snapshot.artifacts,
      selectedArtifactId: snapshot.artifacts[0]?.artifact_id ?? null,
      hitlRequests: snapshot.pending_hitl,
      terminalLogs: snapshot.messages
        .filter((message) => message.event_type === "cli_output" && message.payload)
        .map((message) => message.payload as unknown as TerminalExecutionLogUI)
        .reverse(),
      messages: snapshot.messages.map((message) => ({
        id: message.id,
        roleCode: message.role_code,
        eventType: message.event_type,
        content: message.content,
        payload: message.payload,
      })),
      isRightPaneOpen: true,
      activeRightTab: snapshot.dag_steps.length > 0 && snapshot.artifacts.length === 0 ? "LIVE_DAG" : "ARTIFACT",
      liveAnnouncement: `已還原工作階段 ${snapshot.title}`,
    }),
  resetConversation: () =>
    set({
      sessionId: "",
      sessionTitle: "新的協作",
      activeRoleCode: null,
      dagSteps: [],
      artifacts: [],
      selectedArtifactId: null,
      hitlRequests: [],
      hitlEditor: null,
      messages: [],
      liveAnnouncement: "已開始新的協作。",
    }),
  setSessionId: (sessionId) => set({ sessionId }),
}));

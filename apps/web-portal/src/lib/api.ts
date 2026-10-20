import type { SessionSnapshot } from "@/lib/store/useWorkspaceStore";

export const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const USER_KEY = "eamp-user-id";

export function currentUserId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(USER_KEY);
}

export function rememberUser(id: string): void {
  window.localStorage.setItem(USER_KEY, id);
}

export function forgetUser(): void {
  window.localStorage.removeItem(USER_KEY);
}

function headers(): HeadersInit {
  const id = currentUserId();
  return {
    "Content-Type": "application/json",
    ...(id ? { "X-User-Id": id } : {}),
  };
}

export async function devLogin(input: { email: string; display_name: string; department: string }): Promise<string> {
  const response = await fetch(`${apiBase}/api/v1/users/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error("登入失敗，請稍後再試。");
  const body = (await response.json()) as { id: string };
  rememberUser(body.id);
  return body.id;
}

export interface BootstrapSession {
  id: string;
  title: string;
  status: string;
  active_role_code: string | null;
  hold_reason: string | null;
  updated_at: string;
}

export interface BootstrapMount {
  id: string;
  mount_alias: string;
  browser_handle_key: string | null;
  provider_type: string;
  permission_mode: string;
}

export interface BootstrapPayload {
  sessions: BootstrapSession[];
  mounts: Array<{ mount_id: string; alias: string; handle_key: string | null }>;
  local_workspace_mounts: BootstrapMount[];
  pending_hitl: SessionSnapshot["pending_hitl"];
  notifications: UserNotice[];
}

export interface UserNotice {
  id: string;
  kind: "HEARTBEAT_COMPLETED" | "LOCAL_MOUNT_OFFLINE" | "HITL_REQUIRED" | "HEARTBEAT_FAILED";
  title: string;
  body: string;
  session_id: string | null;
  created_at: string | null;
}

export async function markNotificationRead(id: string): Promise<void> {
  const response = await fetch(`${apiBase}/api/v1/users/me/notifications/${id}/read`, {
    method: "POST",
    headers: headers(),
  });
  if (!response.ok) throw new Error("無法標記通知為已讀。");
}

export interface HeartbeatRoutine {
  id: string;
  title: string;
  role_code: string;
  instructions: string;
  daily_time: string;
  timezone: string;
  is_enabled: boolean;
  last_fired_on: string | null;
}

export async function fetchHeartbeats(): Promise<HeartbeatRoutine[]> {
  const response = await fetch(`${apiBase}/api/v1/heartbeats`, { headers: headers() });
  if (!response.ok) throw new Error("無法載入排程。");
  return (await response.json()) as HeartbeatRoutine[];
}

export async function createHeartbeat(input: {
  title: string;
  role_code: string;
  instructions: string;
  daily_time: string;
}): Promise<HeartbeatRoutine> {
  const response = await fetch(`${apiBase}/api/v1/heartbeats`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(input),
  });
  if (response.status === 404) throw new Error("工作區中找不到這個角色。");
  if (!response.ok) throw new Error("無法建立排程，請確認時間格式為 HH:MM。");
  return (await response.json()) as HeartbeatRoutine;
}

export async function patchHeartbeat(
  id: string,
  input: Partial<Pick<HeartbeatRoutine, "title" | "instructions" | "daily_time" | "is_enabled">>,
): Promise<HeartbeatRoutine> {
  const response = await fetch(`${apiBase}/api/v1/heartbeats/${id}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error("無法更新排程。");
  return (await response.json()) as HeartbeatRoutine;
}

export async function deleteHeartbeat(id: string): Promise<void> {
  const response = await fetch(`${apiBase}/api/v1/heartbeats/${id}`, { method: "DELETE", headers: headers() });
  if (!response.ok) throw new Error("無法刪除排程。");
}

export interface DaemonPairing {
  id: string;
  label: string;
  mount_id: string | null;
  last_connected_at: string | null;
  created_at: string | null;
}

export async function fetchDaemonPairings(): Promise<DaemonPairing[]> {
  const response = await fetch(`${apiBase}/api/v1/daemon/pairings`, { headers: headers() });
  if (!response.ok) throw new Error("無法載入本機 Daemon 配對。");
  return (await response.json()) as DaemonPairing[];
}

export async function createDaemonPairing(label: string): Promise<DaemonPairing & { token: string; command: string }> {
  const response = await fetch(`${apiBase}/api/v1/daemon/pairings`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ label }),
  });
  if (!response.ok) throw new Error("無法產生配對權杖。");
  return (await response.json()) as DaemonPairing & { token: string; command: string };
}

export async function revokeDaemonPairing(id: string): Promise<void> {
  const response = await fetch(`${apiBase}/api/v1/daemon/pairings/${id}`, { method: "DELETE", headers: headers() });
  if (!response.ok) throw new Error("無法撤銷配對。");
}

export async function registerLocalMount(input: {
  mount_alias: string;
  browser_handle_key: string;
  file_tree: Array<{ path: string; size: number; lastModified: number }>;
}): Promise<{ id: string }> {
  const response = await fetch(`${apiBase}/api/v1/mounts/register`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error("無法登記本機資料夾。");
  return (await response.json()) as { id: string };
}

export async function fetchBootstrap(): Promise<BootstrapPayload> {
  const response = await fetch(`${apiBase}/api/v1/users/me/bootstrap`, { headers: headers() });
  if (!response.ok) throw new Error("無法還原工作區，請重新登入。");
  return (await response.json()) as BootstrapPayload;
}

export async function createSession(): Promise<string> {
  const response = await fetch(`${apiBase}/api/v1/chat/sessions`, { method: "POST", headers: headers() });
  if (!response.ok) throw new Error("無法建立對話工作階段。");
  const body = (await response.json()) as { id: string };
  return body.id;
}

export async function fetchState(sessionId: string): Promise<SessionSnapshot> {
  const response = await fetch(`${apiBase}/api/v1/chat/sessions/${sessionId}/state`, { headers: headers() });
  if (!response.ok) throw new Error("無法讀取上次的對話。");
  return (await response.json()) as SessionSnapshot;
}

export interface OrgSkill {
  code: string;
  name: string;
}

export interface OrgTicket {
  id: string;
  title: string;
  status: string;
  tokens_consumed: number;
  token_budget: number;
  created_at: string;
  session_id: string;
}

export interface OrgRole {
  id: string;
  code: string;
  name: string;
  department: string;
  visibility_scope: string;
  reports_to_code: string | null;
  rule_count: number;
  skill_count: number;
  skills: OrgSkill[];
  active_ticket_status: string | null;
  tickets: OrgTicket[];
}

export async function fetchOrgRoles(): Promise<OrgRole[]> {
  const response = await fetch(`${apiBase}/api/v1/org/roles`, { headers: headers() });
  if (!response.ok) throw new Error("無法讀取組織圖。");
  return (await response.json()) as OrgRole[];
}

export async function streamMessage(
  sessionId: string,
  message: string,
  onEvent: (eventType: string, payload: Record<string, unknown>) => void,
): Promise<void> {
  const response = await fetch(`${apiBase}/api/v1/chat/sessions/${sessionId}/stream`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ message }),
  });
  if (!response.ok || !response.body) throw new Error("對話串流沒有開始，請再送一次。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      let eventType = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) eventType = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) onEvent(eventType, JSON.parse(data) as Record<string, unknown>);
    }
  }
}

export interface CatalogRule {
  code: string;
  name: string;
  scope_type: string;
  priority: number;
  rule_content_markdown: string;
  is_visible_to_user: boolean;
}

export interface CatalogSkill {
  code: string;
  name: string;
  trigger_description: string;
  sop_markdown: string;
  execution_mode: string;
  is_visible_to_user: boolean;
}

export interface PromptLayer {
  layer: number;
  heading: string;
  body: string;
}

export async function fetchRules(): Promise<CatalogRule[]> {
  const response = await fetch(`${apiBase}/api/v1/rules`, { headers: headers() });
  if (!response.ok) throw new Error("無法讀取規範。");
  return (await response.json()) as CatalogRule[];
}

export async function fetchSkills(): Promise<CatalogSkill[]> {
  const response = await fetch(`${apiBase}/api/v1/skills`, { headers: headers() });
  if (!response.ok) throw new Error("無法讀取技能。");
  return (await response.json()) as CatalogSkill[];
}

export async function saveSkill(input: {
  code: string;
  name: string;
  trigger_description: string;
  sop_markdown: string;
  execution_mode: string;
}): Promise<void> {
  const response = await fetch(`${apiBase}/api/v1/skills`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error("無法建立技能。");
}

export async function fetchRoleRules(roleCode: string): Promise<CatalogRule[]> {
  const response = await fetch(`${apiBase}/api/v1/roles/${roleCode}/rules`, { headers: headers() });
  if (!response.ok) throw new Error("無法讀取角色規範綁定。");
  return (await response.json()) as CatalogRule[];
}

export async function bindRule(roleCode: string, ruleCode: string): Promise<void> {
  const response = await fetch(`${apiBase}/api/v1/roles/${roleCode}/rules/${ruleCode}`, {
    method: "PUT",
    headers: headers(),
  });
  if (!response.ok) throw new Error("無法綁定規範。");
}

export async function unbindRule(roleCode: string, ruleCode: string): Promise<void> {
  const response = await fetch(`${apiBase}/api/v1/roles/${roleCode}/rules/${ruleCode}`, {
    method: "DELETE",
    headers: headers(),
  });
  if (!response.ok) throw new Error("無法解除規範綁定。");
}

export async function bindSkill(roleCode: string, skillCode: string): Promise<void> {
  const response = await fetch(`${apiBase}/api/v1/roles/${roleCode}/skills/${skillCode}`, {
    method: "PUT",
    headers: headers(),
  });
  if (!response.ok) throw new Error("無法綁定技能。");
}

export async function fetchOnion(roleCode: string): Promise<{ prompt: string; layers: PromptLayer[] }> {
  const response = await fetch(`${apiBase}/api/v1/studio/roles/${roleCode}/prompt`, { headers: headers() });
  if (!response.ok) throw new Error("無法編譯提示詞。");
  return (await response.json()) as { prompt: string; layers: PromptLayer[] };
}

export async function tryRole(roleCode: string, message: string): Promise<{ prompt: string; model_output: unknown; inference_error: string | null }> {
  const response = await fetch(`${apiBase}/api/v1/studio/roles/${roleCode}/try`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ message }),
  });
  if (!response.ok) throw new Error("測試沙盒沒有回應。");
  return (await response.json()) as { prompt: string; model_output: unknown; inference_error: string | null };
}

export interface CatalogTool {
  code: string;
  namespace: string;
  name: string;
  description: string;
  action_tier: string;
  scope_type: string;
  is_enabled: boolean;
}

export async function fetchTools(): Promise<CatalogTool[]> {
  const response = await fetch(`${apiBase}/api/v1/tools`, { headers: headers() });
  if (!response.ok) throw new Error("無法讀取工具。");
  return (await response.json()) as CatalogTool[];
}

export async function decideHitl(
  requestId: string,
  body: { status: "APPROVED" | "MODIFIED" | "REJECTED"; user_modified_payload?: Record<string, unknown>; rejection_reason?: string },
): Promise<{ cli_output: Record<string, unknown> | null }> {
  const response = await fetch(`${apiBase}/api/v1/hitl/${requestId}/decide`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error("無法送出審批決定。");
  const decided = (await response.json()) as { cli_output?: Record<string, unknown> | null };
  return { cli_output: decided.cli_output ?? null };
}

export async function setToolPreference(code: string, isEnabled: boolean): Promise<void> {
  const response = await fetch(`${apiBase}/api/v1/users/me/tool-preferences`, {
    method: "PUT",
    headers: headers(),
    body: JSON.stringify({ code, is_enabled: isEnabled }),
  });
  if (!response.ok) throw new Error("無法更新工具開關。");
}

export interface WorkspaceAgent {
  code: string;
  name: string;
  is_preset: boolean;
  is_enabled: boolean;
  visibility_scope: "PRIVATE" | "DEPARTMENT" | "GLOBAL" | string;
  approval_status: string;
  department: string;
  bound_local_mount_id: string | null;
  system_prompt: string;
  routing_description: string;
}

export interface GeneratedAgentSpec {
  name: string;
  code: string;
  system_prompt: string;
  routing_description: string;
  recommended_rule_codes: string[];
  recommended_skill_codes: string[];
  recommended_tool_codes: string[];
}

async function readError(response: Response, fallback: string): Promise<never> {
  const body = (await response.json().catch(() => null)) as { detail?: string } | null;
  throw new Error(body?.detail || fallback);
}

export async function fetchWorkspaceAgents(): Promise<WorkspaceAgent[]> {
  const response = await fetch(`${apiBase}/api/v1/agents`, { headers: headers() });
  if (!response.ok) return readError(response, "無法讀取 Agent 工作區。");
  return (await response.json()) as WorkspaceAgent[];
}

export async function generateAgentSpec(description: string): Promise<GeneratedAgentSpec> {
  const response = await fetch(`${apiBase}/api/v1/agents/generate-spec`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ description }),
  });
  if (!response.ok) return readError(response, "無法產生 Agent 規格。");
  return (await response.json()) as GeneratedAgentSpec;
}

export async function createAgent(input: {
  code: string;
  name: string;
  department: string;
  system_prompt: string;
  routing_description: string;
  visibility_scope: "PRIVATE" | "DEPARTMENT" | "GLOBAL";
  reports_to_code: string | null;
  bound_local_mount_id: string | null;
  allowed_tool_namespaces: string[];
}): Promise<WorkspaceAgent> {
  const response = await fetch(`${apiBase}/api/v1/agents`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(input),
  });
  if (!response.ok) return readError(response, "無法建立 Agent。");
  return (await response.json()) as WorkspaceAgent;
}

export async function patchAgent(
  code: string,
  input: { is_enabled?: boolean; name?: string; system_prompt?: string },
): Promise<WorkspaceAgent> {
  const response = await fetch(`${apiBase}/api/v1/agents/${code}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify(input),
  });
  if (!response.ok) return readError(response, "無法更新 Agent。");
  return (await response.json()) as WorkspaceAgent;
}

export async function deleteWorkspaceAgent(code: string): Promise<void> {
  const response = await fetch(`${apiBase}/api/v1/agents/${code}`, { method: "DELETE", headers: headers() });
  if (!response.ok) return readError(response, "無法刪除 Agent。");
}

export async function resetPresetAgents(code?: string): Promise<{ restored: string[] }> {
  const response = await fetch(`${apiBase}/api/v1/agents/presets/reset`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(code ? { code } : {}),
  });
  if (!response.ok) return readError(response, "無法還原預設 Agent。");
  return (await response.json()) as { restored: string[] };
}

export async function clearMemories(roleCode?: string): Promise<number> {
  const query = roleCode ? `?role_code=${encodeURIComponent(roleCode)}` : "";
  const response = await fetch(`${apiBase}/api/v1/memories${query}`, { method: "DELETE", headers: headers() });
  if (!response.ok) return readError(response, "無法清理記憶。");
  const body = (await response.json()) as { deleted: number };
  return body.deleted;
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  const response = await fetch(`${apiBase}/api/v1/chat/sessions/${sessionId}`, { method: "DELETE", headers: headers() });
  if (!response.ok) return readError(response, "無法刪除對話工作階段。");
}


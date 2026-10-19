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

export interface BootstrapPayload {
  sessions: BootstrapSession[];
  mounts: Array<{ mount_id: string; alias: string; handle_key: string | null }>;
  pending_hitl: SessionSnapshot["pending_hitl"];
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


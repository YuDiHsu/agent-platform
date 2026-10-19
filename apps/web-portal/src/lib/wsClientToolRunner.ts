// Implements: REQ-004, REQ-007, REQ-010. Disk writes happen only after the user confirms the diff.
import { decideHitl } from "@/lib/api";
import { BrowserLocalFsBridge, isForbiddenLocalPath } from "@/lib/localFsBridge";
import { useWorkspaceStore, type PendingLocalWriteDiff } from "@/lib/store/useWorkspaceStore";

type Waiter = (accepted: boolean) => void;

const waiters = new Map<string, Waiter>();
let grantedWrite: { path: string; content: string } | null = null;
let socket: WebSocket | null = null;

interface RpcRequest {
  jsonrpc?: string;
  id: string;
  method: string;
  params?: {
    browser_handle_key?: string;
    file_path?: string;
    content?: string;
  };
}

function wsBase(): string {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  if (base.startsWith("https://")) return `wss://${base.slice("https://".length)}`;
  if (base.startsWith("http://")) return `ws://${base.slice("http://".length)}`;
  return base;
}

function reply(id: string, body: Record<string, unknown>): void {
  socket?.send(JSON.stringify({ jsonrpc: "2.0", id, ...body }));
}

async function originalText(handleKey: string, path: string): Promise<string> {
  try {
    const file = await BrowserLocalFsBridge.readFileForAgent(handleKey, path);
    return file.encoding === "utf-8" ? file.content : "";
  } catch {
    return "";
  }
}

async function onSocketMessage(raw: string): Promise<void> {
  const message = JSON.parse(raw) as RpcRequest;
  const params = message.params ?? {};
  const path = params.file_path ?? "";
  const handleKey = params.browser_handle_key ?? "";
  if (message.method === "CLIENT_FS_READ" || message.method === "CLIENT_FS_LIST") {
    try {
      if (message.method === "CLIENT_FS_LIST") {
        const root = await BrowserLocalFsBridge.ensurePermission(handleKey, "read");
        const entries = await BrowserLocalFsBridge.scanDirectoryTree(root, path);
        reply(message.id, { result: { entries } });
        return;
      }
      const result = await BrowserLocalFsBridge.readFileForAgent(handleKey, path);
      reply(message.id, { result });
    } catch (caught) {
      const error = caught instanceof Error ? caught.message : "本機讀取失敗";
      reply(message.id, { error: { message: error } });
    }
    return;
  }
  if (message.method !== "CLIENT_FS_WRITE") return;
  if (isForbiddenLocalPath(path)) {
    reply(message.id, { error: { message: `Security Violation: 禁止寫入敏感路徑 (${path})` } });
    return;
  }
  const content = params.content ?? "";
  if (grantedWrite && grantedWrite.path === path && grantedWrite.content === content) {
    try {
      await BrowserLocalFsBridge.commitConfirmedWrite(handleKey, path, content);
      grantedWrite = null;
      reply(message.id, { result: { written: true } });
      useWorkspaceStore.getState().resolvePendingLocalDiff();
    } catch (caught) {
      const error = caught instanceof Error ? caught.message : "本機寫入失敗";
      reply(message.id, { error: { message: error } });
    }
    return;
  }
  const original = await originalText(handleKey, path);
  useWorkspaceStore.getState().openPendingLocalDiff({
    rpc_id: message.id,
    handleKey,
    relativePath: path,
    originalContent: original,
    proposedContent: content,
    executingRole: "AGENT",
  });
  const accepted = await new Promise<boolean>((resolve) => {
    waiters.set(message.id, resolve);
  });
  waiters.delete(message.id);
  if (!accepted) {
    reply(message.id, { error: { message: "使用者取消寫入" } });
    useWorkspaceStore.getState().resolvePendingLocalDiff();
    return;
  }
  try {
    await BrowserLocalFsBridge.commitConfirmedWrite(handleKey, path, content);
    reply(message.id, { result: { written: true } });
  } catch (caught) {
    const error = caught instanceof Error ? caught.message : "本機寫入失敗";
    reply(message.id, { error: { message: error } });
  }
  useWorkspaceStore.getState().resolvePendingLocalDiff();
}

export function startClientToolSocket(sessionId: string, userId: string): () => void {
  if (socket) {
    socket.close();
    socket = null;
  }
  const next = new WebSocket(`${wsBase()}/api/v1/ws/client-tools/${sessionId}?user_id=${userId}`);
  socket = next;
  next.addEventListener("message", (event) => {
    void onSocketMessage(String(event.data));
  });
  return () => {
    if (socket === next) {
      next.close();
      socket = null;
    }
  };
}

export async function confirmDiskWrite(diff: PendingLocalWriteDiff): Promise<void> {
  const waiter = waiters.get(diff.rpc_id);
  if (waiter) {
    waiter(true);
    return;
  }
  if (diff.hitlRequestId) {
    grantedWrite = { path: diff.relativePath, content: diff.proposedContent };
    await decideHitl(diff.hitlRequestId, { status: "APPROVED" });
    useWorkspaceStore.getState().markHitlDecided(diff.hitlRequestId);
    return;
  }
  await BrowserLocalFsBridge.commitConfirmedWrite(diff.handleKey, diff.relativePath, diff.proposedContent);
  useWorkspaceStore.getState().resolvePendingLocalDiff();
}

export async function cancelDiskWrite(diff: PendingLocalWriteDiff): Promise<void> {
  grantedWrite = null;
  const waiter = waiters.get(diff.rpc_id);
  if (waiter) waiter(false);
  if (diff.hitlRequestId) {
    await decideHitl(diff.hitlRequestId, { status: "REJECTED", rejection_reason: "使用者取消寫入本機檔案" });
    useWorkspaceStore.getState().markHitlDecided(diff.hitlRequestId);
  }
  useWorkspaceStore.getState().resolvePendingLocalDiff();
}

import type { HitlRequestUI, PendingLocalWriteDiff } from "@/lib/store/useWorkspaceStore";

export function diffFromHitl(request: HitlRequestUI, handleKey: string): PendingLocalWriteDiff | null {
  if (request.tool_name !== "workspace_write_file") return null;
  const payload = request.proposed_payload;
  return {
    rpc_id: request.hitl_request_id,
    hitlRequestId: request.hitl_request_id,
    handleKey: String(payload.browser_handle_key ?? payload.handle_key ?? handleKey),
    relativePath: String(payload.path ?? payload.file_path ?? ""),
    originalContent: String(payload.original_content ?? ""),
    proposedContent: String(payload.content ?? ""),
    executingRole: request.executing_role_code,
  };
}

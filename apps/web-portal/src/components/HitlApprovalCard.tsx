"use client";

import { RoleBadge } from "@/components/RoleBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { decideHitl } from "@/lib/api";
import { useWorkspaceStore, type HitlRequestUI } from "@/lib/store/useWorkspaceStore";

export function HitlApprovalCard({ request }: { request: HitlRequestUI }) {
  const beginHitlEdit = useWorkspaceStore((state) => state.beginHitlEdit);
  const markHitlDecided = useWorkspaceStore((state) => state.markHitlDecided);
  const pending = request.status === "PENDING";

  async function send(status: "APPROVED" | "REJECTED") {
    await decideHitl(request.hitl_request_id, {
      status,
      rejection_reason: status === "REJECTED" ? "使用者拒絕這次操作" : undefined,
    });
    markHitlDecided(request.hitl_request_id);
  }

  return (
    <article className="hitl-card" aria-labelledby={`hitl-${request.hitl_request_id}`}>
      <header>
        <StatusBadge status="WAITING_HITL" />
        <RoleBadge code={request.executing_role_code} />
      </header>
      <h3 id={`hitl-${request.hitl_request_id}`}>{request.preview_title}</h3>
      <p>
        工具 <strong>{request.tool_name}</strong>
        <span className="badge status-pending">{request.execution_target}</span>
      </p>
      <details>
        <summary>參數預覽</summary>
        <pre>{JSON.stringify(request.proposed_payload, null, 2)}</pre>
      </details>
      <div className="hitl-actions">
        <button type="button" className="quiet-action" disabled={!pending} onClick={() => void send("APPROVED")}>
          核准執行
        </button>
        <button type="button" className="quiet-action" disabled={!pending} onClick={() => beginHitlEdit(request)}>
          在右側修改內容後執行
        </button>
        <button type="button" className="quiet-action danger" disabled={!pending} onClick={() => void send("REJECTED")}>
          拒絕並退回 Agent
        </button>
      </div>
    </article>
  );
}

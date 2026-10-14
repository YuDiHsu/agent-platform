"use client";

import { FileText } from "lucide-react";

import { RoleBadge } from "@/components/RoleBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { useWorkspaceStore, type HitlRequestUI } from "@/lib/store/useWorkspaceStore";

function HitlCard({ request }: { request: HitlRequestUI }) {
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
      <pre>{JSON.stringify(request.proposed_payload, null, 2)}</pre>
      <div className="hitl-actions">
        <button type="button" className="quiet-action" disabled>
          核准執行
        </button>
        <button type="button" className="quiet-action" disabled>
          在右側修改內容後執行
        </button>
        <button type="button" className="quiet-action danger" disabled>
          拒絕並退回 Agent
        </button>
      </div>
      <p className="note" id={`hitl-note-${request.hitl_request_id}`}>
        送出核准會在安全閘門上線後開放。這張卡片會留到你下次登入。
      </p>
    </article>
  );
}

export function ChatStream() {
  const messages = useWorkspaceStore((state) => state.messages);
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const hitlRequests = useWorkspaceStore((state) => state.hitlRequests);
  const selectArtifact = useWorkspaceStore((state) => state.selectArtifact);

  return (
    <div className="stream" aria-live="polite" aria-relevant="additions">
      {messages.length === 0 ? <p className="empty">描述你要完成的工作。主代理會直接回答，或拆成跨角色工單。</p> : null}
      {messages.map((message) => {
        const artifactId =
          message.eventType === "artifact_created" ? String(message.payload?.artifact_id ?? "") : "";
        const artifact = artifacts.find((item) => item.artifact_id === artifactId);
        return (
          <article className="bubble" key={message.id}>
            <header>
              <RoleBadge code={message.roleCode} />
            </header>
            <p>{message.content}</p>
            {artifact ? (
              <div className="claim-card">
                <strong>{artifact.title}</strong>
                <p>{artifact.summary_200_words}</p>
                <button type="button" className="quiet-action" onClick={() => selectArtifact(artifact.artifact_id)}>
                  <FileText size={16} aria-hidden="true" /> 在右側工作區開啟完整規格與圖表
                </button>
              </div>
            ) : null}
          </article>
        );
      })}
      {hitlRequests
        .filter((request) => request.status === "PENDING")
        .map((request) => (
          <HitlCard key={request.hitl_request_id} request={request} />
        ))}
    </div>
  );
}

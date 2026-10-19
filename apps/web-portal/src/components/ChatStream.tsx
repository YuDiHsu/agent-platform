"use client";

import { FileText } from "lucide-react";

import { HitlApprovalCard } from "@/components/HitlApprovalCard";
import { RoleBadge } from "@/components/RoleBadge";
import { useWorkspaceStore } from "@/lib/store/useWorkspaceStore";

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
          <HitlApprovalCard key={request.hitl_request_id} request={request} />
        ))}
    </div>
  );
}

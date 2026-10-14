"use client";

import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";

import "@xyflow/react/dist/style.css";

import { StatusBadge, statusLabel } from "@/components/StatusBadge";
import { currentUserId, fetchOrgRoles, type OrgRole, type OrgTicket } from "@/lib/api";

type AgentNode = Node<{ role: OrgRole }, "agent">;

function AgentOrgNode({ data }: NodeProps<AgentNode>) {
  const role = data.role;
  return (
    <div className="org-node bubble">
      <strong>{role.name}</strong>
      <div>{role.code}</div>
      <span className="badge status-pending">{role.visibility_scope}</span>
      <p>
        規範 {role.rule_count} · 技能 {role.skill_count}
      </p>
      {role.active_ticket_status ? <StatusBadge status={role.active_ticket_status} /> : <p className="note">沒有工單</p>}
    </div>
  );
}

const nodeTypes = { agent: AgentOrgNode };

function depthOf(code: string, roles: Map<string, OrgRole>, seen = new Set<string>()): number {
  if (seen.has(code)) return 0;
  seen.add(code);
  const parent = roles.get(code)?.reports_to_code;
  if (!parent || !roles.has(parent)) return 0;
  return depthOf(parent, roles, seen) + 1;
}

export default function OrgChartPage() {
  const [roles, setRoles] = useState<OrgRole[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"topology" | "kanban">("topology");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (!currentUserId()) {
      setError("請先到協作區登入，才能看你的工單。");
      return;
    }
    void fetchOrgRoles()
      .then(setRoles)
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "無法讀取組織圖"));
  }, []);

  const graph = useMemo(() => {
    const byCode = new Map(roles.map((role) => [role.code, role]));
    const rowCount = new Map<number, number>();
    const nodes: AgentNode[] = roles.map((role) => {
      const depth = depthOf(role.code, byCode);
      const row = rowCount.get(depth) ?? 0;
      rowCount.set(depth, row + 1);
      return {
        id: role.code,
        type: "agent",
        position: { x: depth * 280, y: row * 180 },
        data: { role },
      };
    });
    const edges: Edge[] = roles
      .filter((role) => role.reports_to_code)
      .map((role) => ({
        id: `${role.reports_to_code}-${role.code}`,
        source: role.reports_to_code as string,
        target: role.code,
      }));
    return { nodes, edges };
  }, [roles]);

  const selectedRole = roles.find((role) => role.code === selected) ?? null;
  const tickets = roles.flatMap((role) => role.tickets.map((ticket) => ({ ...ticket, role: role.code })));
  const columns = [
    "PENDING",
    "IN_PROGRESS",
    "WAITING_HITL",
    "WAITING_BROWSER",
    "PAUSED_QUOTA_EXCEEDED",
    "COMPLETED",
    "FAILED",
    "CIRCUIT_BROKEN",
  ];

  return (
    <div className="stage-scroll">
      <h1>組織圖與工單看板</h1>
      <div className="segmented" role="tablist" aria-label="檢視模式">
        <button type="button" className="segment" role="tab" aria-selected={view === "topology"} onClick={() => setView("topology")}>
          代理組織拓撲圖
        </button>
        <button type="button" className="segment" role="tab" aria-selected={view === "kanban"} onClick={() => setView("kanban")}>
          工單看板與 Token 追蹤
        </button>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {view === "topology" ? (
        <div className="org-canvas">
          <ReactFlow
            nodes={graph.nodes}
            edges={graph.edges}
            nodeTypes={nodeTypes}
            nodesFocusable
            onNodeClick={(_event, node) => setSelected(node.id)}
            fitView
          >
            <Background />
            <Controls />
          </ReactFlow>
        </div>
      ) : (
        <div className="kanban">
          {columns.map((status) => (
            <section className="column" key={status} aria-label={statusLabel(status)}>
              <StatusBadge status={status} />
              {tickets
                .filter((ticket) => ticket.status === status)
                .map((ticket: OrgTicket & { role: string }) => (
                  <article className="ticket" key={ticket.id}>
                    <strong>
                      {ticket.role} · {ticket.title}
                    </strong>
                    <p>
                      {ticket.tokens_consumed} / {ticket.token_budget}
                    </p>
                    <div className="meter" aria-hidden="true">
                      <span
                        style={{
                          width: `${Math.min(100, ticket.token_budget === 0 ? 0 : (ticket.tokens_consumed / ticket.token_budget) * 100)}%`,
                        }}
                      />
                    </div>
                  </article>
                ))}
            </section>
          ))}
        </div>
      )}
      {selectedRole ? (
        <>
          <button type="button" className="drawer-backdrop" aria-label="關閉角色抽屜" onClick={() => setSelected(null)} />
          <aside className="sheet right" role="dialog" aria-modal="true" aria-labelledby="role-drawer-title">
            <button type="button" onClick={() => setSelected(null)} autoFocus>
              關閉
            </button>
            <h2 id="role-drawer-title">{selectedRole.name}</h2>
            <p>
              {selectedRole.code} · 向 {selectedRole.reports_to_code ?? "無"} 匯報
            </p>
            <h3>已綁定技能</h3>
            {selectedRole.skills.length === 0 ? <p className="note">沒有綁定技能。</p> : null}
            <ul>
              {selectedRole.skills.map((skill) => (
                <li key={skill.code}>
                  {skill.name}（{skill.code}）
                </li>
              ))}
            </ul>
            <h3>歷史工單</h3>
            {selectedRole.tickets.length === 0 ? <p className="note">這個角色還沒有你的工單。</p> : null}
            <ul>
              {selectedRole.tickets.map((ticket) => (
                <li key={ticket.id}>
                  <StatusBadge status={ticket.status} /> {ticket.title}
                  <div>
                    Token {ticket.tokens_consumed} / {ticket.token_budget}
                  </div>
                  <div className="meter" aria-hidden="true">
                    <span
                      style={{
                        width: `${Math.min(100, ticket.token_budget === 0 ? 0 : (ticket.tokens_consumed / ticket.token_budget) * 100)}%`,
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </aside>
        </>
      ) : null}
    </div>
  );
}

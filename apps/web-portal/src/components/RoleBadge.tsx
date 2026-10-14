const ROLES: Record<string, { label: string; className: string }> = {
  ORCH: { label: "主代理 Orchestrator", className: "role-orch" },
  SA: { label: "系統分析師 SA", className: "role-sa" },
  ARCH: { label: "架構分析師 ARCH", className: "role-arch" },
  SE: { label: "資深工程師 SE", className: "role-se" },
  FIN: { label: "財務專家 FIN", className: "role-fin" },
  PM: { label: "專案經理 PM", className: "role-pm" },
  CEO: { label: "執行長決策代理 CEO", className: "role-ceo" },
  USER: { label: "你", className: "role-user" },
};

export function RoleBadge({ code }: { code: string }) {
  const role = ROLES[code] ?? { label: code, className: "role-user" };
  return <span className={`badge ${role.className}`}>{role.label}</span>;
}

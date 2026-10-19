"use client";

import { useEffect, useState } from "react";

import { currentUserId, fetchTools, setToolPreference, type CatalogTool } from "@/lib/api";

export default function ConnectorsPage() {
  const [signedIn, setSignedIn] = useState(false);
  const [tools, setTools] = useState<CatalogTool[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSignedIn(currentUserId() !== null);
  }, []);

  useEffect(() => {
    if (!signedIn) return;
    void fetchTools()
      .then(setTools)
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "無法載入工具。");
      });
  }, [signedIn]);

  if (!signedIn) {
    return (
      <section className="studio-page">
        <h1>工具與連接器</h1>
        <p>請先到協作區登入，再回來開關你要給代理使用的工具。關閉後會記在你的帳號，下次登入仍然有效。</p>
      </section>
    );
  }

  return (
    <section className="studio-page">
      <h1>工具與連接器</h1>
      <p>這裡只列出你可以開關的工具。系統底層工具不會出現，也不能關閉。</p>
      {error ? <p className="error">{error}</p> : null}
      <ul className="tool-list">
        {tools.map((tool) => (
          <li key={tool.code}>
            <label className="check-row">
              <input
                type="checkbox"
                checked={tool.is_enabled}
                onChange={(event) => {
                  const next = event.target.checked;
                  setTools((current) =>
                    current.map((item) => (item.code === tool.code ? { ...item, is_enabled: next } : item)),
                  );
                  void setToolPreference(tool.code, next).catch((caught: unknown) => {
                    setTools((current) =>
                      current.map((item) => (item.code === tool.code ? { ...item, is_enabled: !next } : item)),
                    );
                    setError(caught instanceof Error ? caught.message : "無法更新工具開關。");
                  });
                }}
              />
              <span>
                <strong>{tool.name}</strong>
                <span className="muted">
                  {tool.namespace} · {tool.action_tier}
                  {tool.scope_type === "ROLE_SCOPED" ? " · 角色限定" : ""}
                </span>
                <span>{tool.description}</span>
              </span>
            </label>
          </li>
        ))}
      </ul>
    </section>
  );
}
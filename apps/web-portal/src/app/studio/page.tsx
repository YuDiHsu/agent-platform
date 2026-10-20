"use client";

import { useEffect, useState } from "react";

import { AgentWizard } from "@/components/studio/AgentWizard";
import { HeartbeatSection } from "@/components/studio/HeartbeatSection";
import { OnionInspector } from "@/components/studio/OnionInspector";
import { RuleBindingSelector } from "@/components/studio/RuleBindingSelector";
import { SkillEditorModal } from "@/components/studio/SkillEditorModal";
import {
  bindRule,
  bindSkill,
  clearMemories,
  currentUserId,
  deleteChatSession,
  deleteWorkspaceAgent,
  fetchOnion,
  fetchRoleRules,
  fetchRules,
  fetchSkills,
  fetchWorkspaceAgents,
  patchAgent,
  resetPresetAgents,
  unbindRule,
  saveSkill,
  tryRole,
  type CatalogRule,
  type CatalogSkill,
  type PromptLayer,
  type WorkspaceAgent,
} from "@/lib/api";

const ROLES = ["ORCH", "CEO", "PM", "FIN", "SA", "ARCH", "SE"];

export default function StudioPage() {
  const [rules, setRules] = useState<CatalogRule[]>([]);
  const [skills, setSkills] = useState<CatalogSkill[]>([]);
  const [selectedRules, setSelectedRules] = useState<string[]>([]);
  const [roleCode, setRoleCode] = useState("SA");
  const [layers, setLayers] = useState<PromptLayer[]>([]);
  const [prompt, setPrompt] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [message, setMessage] = useState("請用三句話說明你的職責邊界。");
  const [trial, setTrial] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(false);
  const [agents, setAgents] = useState<WorkspaceAgent[]>([]);
  const [memoryRole, setMemoryRole] = useState("PM");
  const [sessionToDelete, setSessionToDelete] = useState("");

  async function loadAgents() {
    setAgents(await fetchWorkspaceAgents());
  }

  async function loadPreview(nextRole = roleCode) {
    const onion = await fetchOnion(nextRole);
    setLayers(onion.layers);
    setPrompt(onion.prompt);
  }

  async function loadBindings(nextRole: string) {
    const bound = await fetchRoleRules(nextRole);
    setSelectedRules(bound.filter((rule) => rule.scope_type === "ROLE_EXCLUSIVE").map((rule) => rule.code));
  }

  useEffect(() => {
    setSignedIn(currentUserId() !== null);
  }, []);

  useEffect(() => {
    if (!signedIn) return;
    void (async () => {
      try {
        const [nextRules, nextSkills] = await Promise.all([fetchRules(), fetchSkills(), loadAgents()]);
        setRules(nextRules);
        setSkills(nextSkills);
        await Promise.all([loadBindings("SA"), loadPreview("SA")]);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "無法載入工作坊。");
      }
    })();
  }, [signedIn]);

  if (!signedIn) {
    return (
      <section className="studio-page">
        <h1>自建工作坊</h1>
        <p>請先到協作區登入，再回來綁定規範與檢視洋蔥式提示詞。</p>
      </section>
    );
  }

  return (
    <section className="studio-page">
      <h1>自建工作坊</h1>
      <section className="studio-block">
        <h2>我的 Agent</h2>
        <ul className="roster">
          {agents.map((agent) => (
            <li key={agent.code}>
              <span>
                {agent.name} · {agent.code}
                {agent.approval_status === "PENDING_REVIEW" ? " · 審核中" : ""}
              </span>
              <button type="button" className="ghost" onClick={() => void patchAgent(agent.code, { is_enabled: !agent.is_enabled }).then(loadAgents)}>
                {agent.is_enabled ? "關閉" : "開啟"}
              </button>
              <button type="button" className="ghost" onClick={() => void deleteWorkspaceAgent(agent.code).then(loadAgents)}>
                刪除
              </button>
              {agent.is_preset ? (
                <button type="button" className="ghost" onClick={() => void resetPresetAgents(agent.code).then(loadAgents)}>
                  還原
                </button>
              ) : null}
            </li>
          ))}
        </ul>
        <button type="button" className="text-button primary" onClick={() => void resetPresetAgents().then(loadAgents)}>
          還原系統預設 Agent
        </button>
        <div className="memory-controls">
          <label>
            清理角色記憶
            <select value={memoryRole} onChange={(event) => setMemoryRole(event.target.value)}>
              {agents.map((agent) => (
                <option key={agent.code} value={agent.code}>
                  {agent.code}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="ghost" onClick={() => void clearMemories(memoryRole)}>
            清理此角色記憶
          </button>
          <label>
            刪除對話工作階段
            <input value={sessionToDelete} onChange={(event) => setSessionToDelete(event.target.value)} placeholder="session id" />
          </label>
          <button
            type="button"
            className="ghost"
            disabled={sessionToDelete.trim().length === 0}
            onClick={() => void deleteChatSession(sessionToDelete.trim()).then(() => setSessionToDelete(""))}
          >
            刪除對話與暫時切片
          </button>
          <button type="button" className="ghost" onClick={() => void clearMemories()}>
            清理個人記憶
          </button>
        </div>
      </section>
      <HeartbeatSection agents={agents} />
      <AgentWizard agents={agents} rules={rules} skills={skills} onCreated={loadAgents} />
      <div className="studio-grid">
        <div>
          <label>
            角色
            <select
              value={roleCode}
              onChange={(event) => {
                const next = event.target.value;
                setRoleCode(next);
                void Promise.all([loadBindings(next), loadPreview(next)]).catch((caught: unknown) => {
                  setError(caught instanceof Error ? caught.message : "無法編譯提示詞。");
                });
              }}
            >
              {(agents.length > 0 ? agents.map((agent) => agent.code) : ROLES).map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </label>
          <RuleBindingSelector
            rules={rules}
            selected={selectedRules}
            onToggle={(code) => {
              const bound = selectedRules.includes(code);
              const request = bound ? unbindRule(roleCode, code) : bindRule(roleCode, code);
              void request
                .then(() => Promise.all([loadBindings(roleCode), loadPreview(roleCode)]))
                .catch((caught: unknown) => {
                  setError(caught instanceof Error ? caught.message : "無法更新規範綁定。");
                });
            }}
          />
          <h2>技能</h2>
          <ul>
            {skills.map((skill) => (
              <li key={skill.code}>
                {skill.name}
                <button type="button" className="ghost" onClick={() => void bindSkill(roleCode, skill.code).then(() => loadPreview())}>
                  綁定到 {roleCode}
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className="text-button primary" onClick={() => setEditorOpen(true)}>
            新增技能
          </button>
        </div>
        <div>
          <OnionInspector layers={layers} prompt={prompt} />
          <form
            className="studio-block"
            onSubmit={(event) => {
              event.preventDefault();
              void tryRole(roleCode, message)
                .then((result) => {
                  setPrompt(result.prompt);
                  setTrial(result.inference_error ?? JSON.stringify(result.model_output, null, 2));
                })
                .catch((caught: unknown) => {
                  setTrial(caught instanceof Error ? caught.message : "測試失敗。");
                });
            }}
          >
            <h2>測試沙盒</h2>
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} />
            <button type="submit" className="text-button primary">
              送出測試
            </button>
            {trial ? <pre>{trial}</pre> : null}
          </form>
        </div>
      </div>
      {error ? <p className="error">{error}</p> : null}
      <SkillEditorModal
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        onSave={async (input) => {
          await saveSkill({ ...input, execution_mode: "PROMPT_ONLY" });
          setSkills(await fetchSkills());
          setEditorOpen(false);
        }}
      />
    </section>
  );
}

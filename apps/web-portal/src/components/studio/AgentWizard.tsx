"use client";

import { FormEvent, useState } from "react";

import {
  bindRule,
  bindSkill,
  createAgent,
  fetchBootstrap,
  fetchTools,
  generateAgentSpec,
  registerLocalMount,
  type CatalogRule,
  type CatalogSkill,
  type CatalogTool,
  type WorkspaceAgent,
} from "@/lib/api";
import { BrowserLocalFsBridge, directoryPickerSupported } from "@/lib/localFsBridge";

const STEPS = ["一句話", "身分與範圍", "工具與資料夾", "規範與技能"] as const;

export function AgentWizard({
  agents,
  rules,
  skills,
  onCreated,
}: {
  agents: WorkspaceAgent[];
  rules: CatalogRule[];
  skills: CatalogSkill[];
  onCreated: () => Promise<void>;
}) {
  const [step, setStep] = useState(0);
  const [description, setDescription] = useState("");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [department, setDepartment] = useState("RD");
  const [reportsTo, setReportsTo] = useState("");
  const [visibility, setVisibility] = useState<"PRIVATE" | "DEPARTMENT" | "GLOBAL">("PRIVATE");
  const [prompt, setPrompt] = useState("");
  const [routing, setRouting] = useState("");
  const [tools, setTools] = useState<CatalogTool[]>([]);
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [mountId, setMountId] = useState("");
  const [mounts, setMounts] = useState<Array<{ id: string; mount_alias: string }>>([]);
  const [selectedRules, setSelectedRules] = useState<string[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const lockedPrivate = mountId !== "";

  async function generate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const spec = await generateAgentSpec(description);
      setName(spec.name);
      setCode(spec.code);
      setPrompt(spec.system_prompt);
      setRouting(spec.routing_description);
      setSelectedRules(spec.recommended_rule_codes);
      setSelectedSkills(spec.recommended_skill_codes);
      setSelectedTools(spec.recommended_tool_codes);
      setStep(1);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "無法產生規格");
    } finally {
      setBusy(false);
    }
  }

  async function loadStepThree() {
    const [toolRows, boot] = await Promise.all([fetchTools(), fetchBootstrap()]);
    setTools(toolRows);
    setMounts(boot.local_workspace_mounts ?? []);
  }

  async function mountFolder() {
    if (!directoryPickerSupported()) {
      setError("請使用桌面版 Chrome 或 Microsoft Edge 授權本機資料夾。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const mounted = await BrowserLocalFsBridge.authorizeAndMountDirectory();
      const saved = await registerLocalMount({
        mount_alias: mounted.folderName,
        browser_handle_key: mounted.handleKey,
        file_tree: mounted.fileTree,
      });
      setMounts((current) => [...current, { id: saved.id, mount_alias: mounted.folderName }]);
      setMountId(saved.id);
      setVisibility("PRIVATE");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "無法掛載資料夾");
    } finally {
      setBusy(false);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const namespaces = tools.filter((tool) => selectedTools.includes(tool.code)).map((tool) => tool.namespace);
      const created = await createAgent({
        code,
        name,
        department,
        system_prompt: prompt,
        routing_description: routing,
        visibility_scope: lockedPrivate ? "PRIVATE" : visibility,
        reports_to_code: reportsTo || null,
        bound_local_mount_id: mountId || null,
        allowed_tool_namespaces: [...new Set(namespaces)],
      });
      await Promise.all([
        ...selectedRules.map((ruleCode) => bindRule(created.code, ruleCode)),
        ...selectedSkills.map((skillCode) => bindSkill(created.code, skillCode)),
      ]);
      await onCreated();
      setStep(0);
      setDescription("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "無法建立 Agent");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="wizard" onSubmit={step === 0 ? (event) => void generate(event) : step === 3 ? (event) => void save(event) : (event) => event.preventDefault()}>
      <h2>建立 Agent</h2>
      <ol className="wizard-steps">
        {STEPS.map((label, index) => (
          <li key={label} aria-current={index === step ? "step" : undefined}>
            {index + 1}. {label}
          </li>
        ))}
      </ol>
      {step === 0 ? (
        <label>
          用一句話描述這個 Agent
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} required />
        </label>
      ) : null}
      {step === 1 ? (
        <>
          <label>
            名稱
            <input value={name} onChange={(event) => setName(event.target.value)} required />
          </label>
          <label>
            代碼
            <input value={code} onChange={(event) => setCode(event.target.value)} required />
          </label>
          <label>
            部門
            <input value={department} onChange={(event) => setDepartment(event.target.value)} required />
          </label>
          <label>
            上層 Agent
            <select value={reportsTo} onChange={(event) => setReportsTo(event.target.value)}>
              <option value="">沒有</option>
              {agents.map((agent) => (
                <option key={agent.code} value={agent.code}>
                  {agent.name}
                </option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>發布範圍</legend>
            {(["PRIVATE", "DEPARTMENT", "GLOBAL"] as const).map((scope) => (
              <label key={scope}>
                <input
                  type="radio"
                  name="visibility"
                  checked={(lockedPrivate ? "PRIVATE" : visibility) === scope}
                  disabled={lockedPrivate && scope !== "PRIVATE"}
                  onChange={() => setVisibility(scope)}
                />
                {scope}
              </label>
            ))}
            {lockedPrivate ? <p className="note">為保護您的電腦檔案安全，綁定本機資料夾的 Agent 強制設為個人私有。</p> : null}
          </fieldset>
          <label>
            系統提示詞
            <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} required />
          </label>
        </>
      ) : null}
      {step === 2 ? (
        <>
          <fieldset>
            <legend>工具與連接器</legend>
            {tools.map((tool) => (
              <label key={tool.code}>
                <input
                  type="checkbox"
                  checked={selectedTools.includes(tool.code)}
                  onChange={() =>
                    setSelectedTools((current) =>
                      current.includes(tool.code) ? current.filter((item) => item !== tool.code) : [...current, tool.code],
                    )
                  }
                />
                {tool.name}
              </label>
            ))}
          </fieldset>
          <label>
            本機資料夾
            <select
              value={mountId}
              onChange={(event) => {
                setMountId(event.target.value);
                if (event.target.value) setVisibility("PRIVATE");
              }}
            >
              <option value="">不綁定</option>
              {mounts.map((mount) => (
                <option key={mount.id} value={mount.id}>
                  {mount.mount_alias}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="ghost" disabled={busy} onClick={() => void mountFolder()}>
            新增掛載本機資料夾
          </button>
        </>
      ) : null}
      {step === 3 ? (
        <>
          <fieldset>
            <legend>規範</legend>
            {rules.map((rule) => (
              <label key={rule.code}>
                <input
                  type="checkbox"
                  checked={selectedRules.includes(rule.code)}
                  onChange={() =>
                    setSelectedRules((current) =>
                      current.includes(rule.code) ? current.filter((item) => item !== rule.code) : [...current, rule.code],
                    )
                  }
                />
                {rule.name}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>技能</legend>
            {skills.map((skill) => (
              <label key={skill.code}>
                <input
                  type="checkbox"
                  checked={selectedSkills.includes(skill.code)}
                  onChange={() =>
                    setSelectedSkills((current) =>
                      current.includes(skill.code) ? current.filter((item) => item !== skill.code) : [...current, skill.code],
                    )
                  }
                />
                {skill.name}
              </label>
            ))}
          </fieldset>
        </>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
      <div className="hitl-actions">
        {step === 0 ? (
          <button type="submit" className="text-button primary" disabled={busy || description.trim().length === 0}>
            呼叫 Gemma 4 自動生成規格
          </button>
        ) : (
          <button type="button" className="ghost" onClick={() => setStep((value) => value - 1)}>
            上一步
          </button>
        )}
        {step > 0 && step < 3 ? (
          <button
            type="button"
            className="text-button primary"
            onClick={() => {
              if (step === 1) void loadStepThree().then(() => setStep(2));
              else setStep(3);
            }}
          >
            下一步
          </button>
        ) : null}
        {step === 3 ? (
          <button type="submit" className="text-button primary" disabled={busy}>
            建立 Agent
          </button>
        ) : null}
      </div>
    </form>
  );
}

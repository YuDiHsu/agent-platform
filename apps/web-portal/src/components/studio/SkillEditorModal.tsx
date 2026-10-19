"use client";

import { useState } from "react";

export function SkillEditorModal({
  open,
  onClose,
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  onSave: (input: { code: string; name: string; trigger_description: string; sop_markdown: string }) => Promise<void>;
}) {
  const [code, setCode] = useState("SKILL_CUSTOM_NOTE");
  const [name, setName] = useState("自訂筆記");
  const [trigger, setTrigger] = useState("需要把討論整理成短筆記時使用。");
  const [sop, setSop] = useState("只根據已提供的內容整理，不補寫未出現的結論。");
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <form
        className="modal-card"
        role="dialog"
        aria-labelledby="skill-editor-title"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          void onSave({ code, name, trigger_description: trigger, sop_markdown: sop }).catch((caught: unknown) => {
            setError(caught instanceof Error ? caught.message : "無法儲存技能。");
          });
        }}
      >
        <h2 id="skill-editor-title">新增技能</h2>
        <label>
          代碼
          <input value={code} onChange={(event) => setCode(event.target.value)} required />
        </label>
        <label>
          名稱
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label>
          觸發說明
          <input value={trigger} onChange={(event) => setTrigger(event.target.value)} maxLength={300} required />
        </label>
        <label>
          SOP
          <textarea value={sop} onChange={(event) => setSop(event.target.value)} required />
        </label>
        {error ? <p className="error">{error}</p> : null}
        <div className="modal-actions">
          <button type="button" className="ghost" onClick={onClose}>
            取消
          </button>
          <button type="submit" className="text-button primary">
            儲存
          </button>
        </div>
      </form>
    </div>
  );
}

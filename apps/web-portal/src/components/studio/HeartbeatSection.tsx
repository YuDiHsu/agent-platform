"use client";

import { useEffect, useState } from "react";

import {
  createHeartbeat,
  deleteHeartbeat,
  fetchHeartbeats,
  patchHeartbeat,
  type HeartbeatRoutine,
  type WorkspaceAgent,
} from "@/lib/api";

const MORNING_BRIEF = {
  title: "晨間摘要",
  role_code: "PM",
  instructions: "分類今天的未讀信件，整理成晨間摘要並草擬 Teams 訊息。",
  daily_time: "08:30",
};

export function HeartbeatSection({ agents }: { agents: WorkspaceAgent[] }) {
  const [routines, setRoutines] = useState<HeartbeatRoutine[]>([]);
  const [draft, setDraft] = useState(MORNING_BRIEF);
  const [error, setError] = useState<string | null>(null);
  const roles = agents.filter((agent) => agent.is_enabled && agent.code !== "ORCH");

  async function load() {
    setRoutines(await fetchHeartbeats());
  }

  useEffect(() => {
    void load().catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "無法載入排程。"));
  }, []);

  function run(action: Promise<unknown>) {
    setError(null);
    void action.then(load).catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : "無法更新排程。");
    });
  }

  return (
    <section className="studio-block" aria-labelledby="heartbeat-heading">
      <h2 id="heartbeat-heading">排程</h2>
      <p className="muted">每天到了設定時間（台北時間），背景 Worker 會替你建立一張工單，關掉瀏覽器也照常執行，完成後會留下通知。</p>
      {routines.length === 0 ? (
        <p>還沒有排程。下面已經填好晨間摘要範本，可以直接新增。</p>
      ) : (
        <ul className="roster">
          {routines.map((routine) => (
            <li key={routine.id}>
              <span>
                <strong>{routine.daily_time}</strong> {routine.title} · {routine.role_code}
                {routine.last_fired_on ? ` · 上次執行 ${routine.last_fired_on}` : ""}
                {routine.is_enabled ? "" : " · 已暫停"}
              </span>
              <button
                type="button"
                className="ghost"
                onClick={() => run(patchHeartbeat(routine.id, { is_enabled: !routine.is_enabled }))}
              >
                {routine.is_enabled ? "暫停" : "啟用"}
              </button>
              <button type="button" className="ghost" onClick={() => run(deleteHeartbeat(routine.id))}>
                刪除
              </button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="heartbeat-form"
        onSubmit={(event) => {
          event.preventDefault();
          run(createHeartbeat(draft));
        }}
      >
        <label>
          名稱
          <input required value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
        </label>
        <label>
          每天
          <input
            type="time"
            required
            value={draft.daily_time}
            onChange={(event) => setDraft({ ...draft, daily_time: event.target.value })}
          />
        </label>
        <label>
          角色
          <select value={draft.role_code} onChange={(event) => setDraft({ ...draft, role_code: event.target.value })}>
            {(roles.length > 0 ? roles.map((agent) => agent.code) : [draft.role_code]).map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
        <label className="wide">
          要做的事
          <textarea
            required
            value={draft.instructions}
            onChange={(event) => setDraft({ ...draft, instructions: event.target.value })}
          />
        </label>
        <button type="submit" className="text-button primary">
          新增排程
        </button>
      </form>
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}

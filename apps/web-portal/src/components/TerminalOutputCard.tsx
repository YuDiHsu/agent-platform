"use client";

import { parseAnsi } from "@/lib/ansi";
import type { TerminalExecutionLogUI } from "@/lib/store/useWorkspaceStore";

const TARGET_LABEL: Record<TerminalExecutionLogUI["execution_target"], string> = {
  SERVER_SANDBOX_CLI: "SERVER_SANDBOX_CLI",
  LOCAL_DAEMON_CLI: "LOCAL_DAEMON_CLI",
};

function AnsiText({ text, label }: { text: string; label: string }) {
  return (
    <pre className="terminal-stream" aria-label={label}>
      {parseAnsi(text).map((span, index) => (
        <span key={index} className={span.className}>
          {span.text}
        </span>
      ))}
    </pre>
  );
}

export function TerminalOutputCard({ log }: { log: TerminalExecutionLogUI }) {
  const ok = log.exit_code === 0;
  return (
    <article className="terminal-card" aria-label={`終端機輸出 ${log.skill_code}`}>
      <header className="terminal-head">
        <span className="badge status-pending">[{TARGET_LABEL[log.execution_target]}]</span>
        <span className={ok ? "badge status-done" : "badge status-failed"}>
          {ok ? "成功" : "失敗"} · exit {log.exit_code ?? "?"}
        </span>
        {typeof log.duration_ms === "number" ? <span className="note">{log.duration_ms} ms</span> : null}
      </header>
      <code className="terminal-command">$ {log.command}</code>
      {log.stdout ? <AnsiText text={log.stdout} label="標準輸出" /> : null}
      {log.stderr ? <AnsiText text={log.stderr} label="標準錯誤" /> : null}
    </article>
  );
}

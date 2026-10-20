"use client";

import { useEffect, useState } from "react";

import { createDaemonPairing, fetchDaemonPairings, revokeDaemonPairing, type DaemonPairing } from "@/lib/api";

export function DaemonPairingSection() {
  const [pairings, setPairings] = useState<DaemonPairing[]>([]);
  const [label, setLabel] = useState("我的電腦");
  const [issued, setIssued] = useState<{ label: string; command: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setPairings(await fetchDaemonPairings());
  }

  useEffect(() => {
    void load().catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "無法載入配對。"));
  }, []);

  return (
    <section className="studio-block" aria-labelledby="daemon-heading">
      <h2 id="daemon-heading">本機 Daemon（選配）</h2>
      <p className="muted">
        在電腦上執行 Local MCP Daemon 後，瀏覽器關閉時背景工作仍能讀寫你開放的資料夾，並執行本機 CLI/Git 診斷。Daemon
        只能存取啟動時指定的資料夾，.env、金鑰與 .git 內容一律拒絕。
      </p>
      {pairings.length > 0 ? (
        <ul className="roster">
          {pairings.map((pairing) => (
            <li key={pairing.id}>
              <span>
                <strong>{pairing.label}</strong>
                {pairing.last_connected_at
                  ? ` · 上次連線 ${new Date(pairing.last_connected_at).toLocaleString("zh-TW")}`
                  : " · 尚未連線"}
              </span>
              <button
                type="button"
                className="ghost"
                onClick={() =>
                  void revokeDaemonPairing(pairing.id)
                    .then(load)
                    .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "無法撤銷配對。"))
                }
              >
                撤銷
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <form
        className="daemon-form"
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          setCopied(false);
          void createDaemonPairing(label.trim())
            .then((created) => {
              setIssued({ label: created.label, command: created.command });
              return load();
            })
            .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : "無法產生配對權杖。"));
        }}
      >
        <label>
          這台電腦的名稱
          <input required maxLength={100} value={label} onChange={(event) => setLabel(event.target.value)} />
        </label>
        <button type="submit" className="text-button primary" disabled={label.trim().length === 0}>
          產生配對權杖
        </button>
      </form>
      {issued ? (
        <div className="daemon-issued" role="status">
          <p>
            「{issued.label}」的權杖只會顯示這一次。在專案根目錄執行下面的指令，並把 <code>&lt;本機資料夾&gt;</code>{" "}
            換成要開放的資料夾：
          </p>
          <pre>{issued.command}</pre>
          <button
            type="button"
            className="ghost"
            onClick={() =>
              void navigator.clipboard.writeText(issued.command).then(
                () => setCopied(true),
                () => setError("無法複製，請手動選取指令。"),
              )
            }
          >
            {copied ? "已複製" : "複製指令"}
          </button>
        </div>
      ) : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}

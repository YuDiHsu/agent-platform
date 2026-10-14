"use client";

import { FormEvent, useEffect, useState } from "react";

import { ChatStream } from "@/components/ChatStream";
import { MiniDagProgressBar } from "@/components/MiniDagProgressBar";
import { createSession, currentUserId, devLogin, fetchBootstrap, fetchState, streamMessage } from "@/lib/api";
import { useWorkspaceStore } from "@/lib/store/useWorkspaceStore";

export default function ChatPage() {
  const [email, setEmail] = useState("pilot@hub.local");
  const [displayName, setDisplayName] = useState("王小明");
  const [department, setDepartment] = useState("RD");
  const [signedIn, setSignedIn] = useState(false);
  const [draft, setDraft] = useState("");
  const [roleHint, setRoleHint] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const appendMessage = useWorkspaceStore((state) => state.appendMessage);
  const handleSSEEvent = useWorkspaceStore((state) => state.handleSSEEvent);
  const hydrate = useWorkspaceStore((state) => state.hydrate);
  const resetConversation = useWorkspaceStore((state) => state.resetConversation);
  const sessionId = useWorkspaceStore((state) => state.sessionId);
  const setSessionId = useWorkspaceStore((state) => state.setSessionId);

  useEffect(() => {
    if (!currentUserId()) return;
    setSignedIn(true);
    void (async () => {
      try {
        const boot = await fetchBootstrap();
        const latest = boot.sessions[0];
        if (!latest) return;
        hydrate(await fetchState(latest.id));
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "無法還原工作區");
      }
    })();
  }, [hydrate]);

  async function onLogin(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await devLogin({ email, display_name: displayName, department });
      setSignedIn(true);
      const boot = await fetchBootstrap();
      if (boot.sessions[0]) hydrate(await fetchState(boot.sessions[0].id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "登入失敗");
    }
  }

  async function onSend(event: FormEvent) {
    event.preventDefault();
    const message = `${roleHint}${draft}`.trim();
    if (!message || busy) return;
    setBusy(true);
    setError(null);
    appendMessage({
      id: crypto.randomUUID(),
      roleCode: "USER",
      eventType: "user_message",
      content: message,
    });
    setDraft("");
    try {
      let id = sessionId;
      if (!id) {
        id = await createSession();
        setSessionId(id);
      }
      await streamMessage(id, message, handleSSEEvent);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "送出失敗，請再試一次。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="stage-scroll">
        {!signedIn ? (
          <form className="signin" onSubmit={(event) => void onLogin(event)}>
            <h1>回到你的工作區</h1>
            <p className="note">用公司信箱進入。關閉瀏覽器後，下次登入會還原上次的對話、工單與產出物。</p>
            <label>
              信箱
              <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required />
            </label>
            <label>
              姓名
              <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required />
            </label>
            <label>
              部門
              <input value={department} onChange={(event) => setDepartment(event.target.value)} required />
            </label>
            {error ? <p className="error">{error}</p> : null}
            <button className="text-button primary" type="submit">
              進入工作區
            </button>
          </form>
        ) : (
          <>
            <MiniDagProgressBar />
            <ChatStream />
          </>
        )}
      </div>
      {signedIn ? (
        <form className="composer" onSubmit={(event) => void onSend(event)}>
          <div className="composer-tools">
            <label>
              本機掛載
              <select disabled defaultValue="">
                <option value="">尚未掛載本機資料夾</option>
              </select>
            </label>
            <label>
              指定角色
              <select value={roleHint} onChange={(event) => setRoleHint(event.target.value)}>
                <option value="">交給主代理判斷</option>
                <option value="請 PM：">PM</option>
                <option value="請 SA：">SA</option>
                <option value="請 ARCH：">ARCH</option>
                <option value="請 FIN：">FIN</option>
              </select>
            </label>
            <button
              type="button"
              onClick={() => {
                resetConversation();
                setError(null);
              }}
            >
              新的協作
            </button>
          </div>
          <label htmlFor="composer-input">輸入指令</label>
          <textarea
            id="composer-input"
            value={draft}
            placeholder="描述要完成的工作。Enter 送出，Shift+Enter 換行。"
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <div className="composer-row">
            {error ? <p className="error">{error}</p> : <p className="note">主代理會決定直接回答，或拆成 DAG。</p>}
            <button className="send-button" type="submit" disabled={busy || draft.trim().length === 0}>
              {busy ? "傳送中" : "發送"}
            </button>
          </div>
        </form>
      ) : null}
    </>
  );
}

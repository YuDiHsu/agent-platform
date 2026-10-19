"use client";

import { FormEvent, useEffect, useState } from "react";

import { ChatStream } from "@/components/ChatStream";
import { MiniDagProgressBar } from "@/components/MiniDagProgressBar";
import {
  createSession,
  currentUserId,
  devLogin,
  fetchBootstrap,
  fetchState,
  registerLocalMount,
  streamMessage,
  type BootstrapMount,
} from "@/lib/api";
import { BrowserLocalFsBridge, directoryPickerSupported, UNSUPPORTED_DIRECTORY_GUIDANCE } from "@/lib/localFsBridge";
import { diffFromHitl } from "@/lib/localWrite";
import { useWorkspaceStore, type MountedFolder } from "@/lib/store/useWorkspaceStore";
import { startClientToolSocket } from "@/lib/wsClientToolRunner";

async function restoreMounts(mounts: BootstrapMount[]): Promise<MountedFolder[]> {
  return Promise.all(
    mounts.map(async (mount) => {
      const handleKey = mount.browser_handle_key ?? "";
      const state = handleKey ? await BrowserLocalFsBridge.inspectHandle(handleKey) : "missing";
      return {
        mountId: mount.id,
        alias: mount.mount_alias,
        handleKey,
        isConnected: state === "connected",
        needsPermission: state === "needs-permission",
        fileCount: 0,
      };
    }),
  );
}

function LocalFolderControl({
  folders,
  onChange,
  onError,
}: {
  folders: MountedFolder[];
  onChange: (folders: MountedFolder[]) => void;
  onError: (message: string | null) => void;
}) {
  const [working, setWorking] = useState(false);
  const [support, setSupport] = useState<"unknown" | "ready" | "unsupported">("unknown");
  const connected = folders.find((folder) => folder.isConnected);
  const pending = folders.filter((folder) => folder.needsPermission);

  useEffect(() => {
    setSupport(directoryPickerSupported() ? "ready" : "unsupported");
  }, []);

  if (support === "unknown") return null;
  if (support === "unsupported") {
    return <p className="note">{UNSUPPORTED_DIRECTORY_GUIDANCE}</p>;
  }

  async function authorize() {
    setWorking(true);
    onError(null);
    try {
      const mounted = await BrowserLocalFsBridge.authorizeAndMountDirectory();
      const saved = await registerLocalMount({
        mount_alias: mounted.folderName,
        browser_handle_key: mounted.handleKey,
        file_tree: mounted.fileTree,
      });
      onChange([
        ...folders,
        {
          mountId: saved.id,
          alias: mounted.folderName,
          handleKey: mounted.handleKey,
          isConnected: true,
          needsPermission: false,
          fileCount: mounted.fileTree.length,
        },
      ]);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "無法授權本機資料夾");
    } finally {
      setWorking(false);
    }
  }

  async function restore(folder: MountedFolder) {
    setWorking(true);
    onError(null);
    try {
      await BrowserLocalFsBridge.ensurePermission(folder.handleKey, "readwrite");
      onChange(
        folders.map((item) =>
          item.mountId === folder.mountId ? { ...item, isConnected: true, needsPermission: false } : item,
        ),
      );
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "無法恢復本機資料夾連線");
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="mount-control">
      <label>
        本機掛載
        <select value={connected?.mountId ?? folders[0]?.mountId ?? ""} onChange={() => undefined}>
          {folders.length === 0 ? <option value="">尚未掛載本機資料夾</option> : null}
          {folders.map((folder) => (
            <option key={folder.mountId} value={folder.mountId}>
              {folder.alias}
              {folder.isConnected ? "" : "（未連線）"}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className="ghost" disabled={working} onClick={() => void authorize()}>
        授權本機資料夾
      </button>
      {pending.map((folder) => (
        <button key={folder.mountId} type="button" className="ghost" disabled={working} onClick={() => void restore(folder)}>
          恢復本機資料夾連線
        </button>
      ))}
    </div>
  );
}

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
  const mountedFolders = useWorkspaceStore((state) => state.mountedFolders);
  const setMountedFolders = useWorkspaceStore((state) => state.setMountedFolders);
  const openPendingLocalDiff = useWorkspaceStore((state) => state.openPendingLocalDiff);

  async function openWorkspace(boot: Awaited<ReturnType<typeof fetchBootstrap>>) {
    const folders = await restoreMounts(boot.local_workspace_mounts ?? []);
    setMountedFolders(folders);
    const latest = boot.sessions[0];
    if (!latest) return;
    const snapshot = await fetchState(latest.id);
    hydrate(snapshot);
    const write = snapshot.pending_hitl.find((item) => item.tool_name === "workspace_write_file");
    const handleKey = folders.find((folder) => folder.isConnected)?.handleKey ?? folders[0]?.handleKey ?? "";
    if (!write) return;
    const diff = diffFromHitl(write, handleKey);
    if (diff) openPendingLocalDiff(diff);
  }

  useEffect(() => {
    if (!currentUserId()) return;
    setSignedIn(true);
    void (async () => {
      try {
        await openWorkspace(await fetchBootstrap());
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "無法還原工作區");
      }
    })();
    // Restore once when the signed-in page mounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!signedIn || !sessionId) return;
    const userId = currentUserId();
    if (!userId) return;
    return startClientToolSocket(sessionId, userId);
  }, [signedIn, sessionId]);

  async function onLogin(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await devLogin({ email, display_name: displayName, department });
      setSignedIn(true);
      await openWorkspace(await fetchBootstrap());
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
            <p className="lede">用公司信箱進入。關閉瀏覽器之後，下次登入會還原上次的對話、工單與產出物。</p>
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
            <LocalFolderControl folders={mountedFolders} onChange={setMountedFolders} onError={setError} />
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
              className="ghost"
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

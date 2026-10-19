"use client";

import { useEffect, useId, useRef, useState } from "react";
import ReactDiffViewer from "react-diff-viewer-continued";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { decideHitl } from "@/lib/api";
import { BrowserLocalFsBridge } from "@/lib/localFsBridge";
import { cancelDiskWrite, confirmDiskWrite } from "@/lib/wsClientToolRunner";
import { useWorkspaceStore, type HitlRequestUI, type RightPaneTab } from "@/lib/store/useWorkspaceStore";

const TABS: Array<{ id: RightPaneTab; label: string }> = [
  { id: "ARTIFACT", label: "產出物" },
  { id: "FILE_DIFF", label: "差異" },
  { id: "TERMINAL_CLI", label: "終端機" },
  { id: "LIVE_DAG", label: "即時 DAG" },
  { id: "PROMPT_INSPECTOR", label: "提示詞" },
];

function MermaidBlock({ code }: { code: string }) {
  const reactId = useId().replace(/:/g, "");
  const [svg, setSvg] = useState("");
  const [error, setError] = useState("");
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    void import("mermaid").then(async (module) => {
      const mermaid = module.default;
      mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "neutral" });
      try {
        const rendered = await mermaid.render(`mermaid-${reactId}`, code);
        if (!cancelled) setSvg(rendered.svg);
      } catch {
        if (!cancelled) setError("這段 Mermaid 圖無法繪製。");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [code, reactId]);

  return (
    <figure>
      <figcaption className="diagram-toolbar">
        <button type="button" onClick={() => setScale((value) => Math.min(2.4, value + 0.2))}>
          放大
        </button>
        <button type="button" onClick={() => setScale((value) => Math.max(0.4, value - 0.2))}>
          縮小
        </button>
        <button
          type="button"
          onClick={() => {
            setScale(1);
            setOffset({ x: 0, y: 0 });
          }}
        >
          重設
        </button>
        <button type="button" onClick={() => setOffset((value) => ({ ...value, y: value.y - 24 }))}>
          上移
        </button>
        <button type="button" onClick={() => setOffset((value) => ({ ...value, y: value.y + 24 }))}>
          下移
        </button>
      </figcaption>
      {error ? <p className="error">{error}</p> : null}
      <div
        className="diagram-frame"
        onPointerDown={(event) => {
          drag.current = { x: event.clientX - offset.x, y: event.clientY - offset.y };
        }}
        onPointerMove={(event) => {
          if (!drag.current) return;
          setOffset({ x: event.clientX - drag.current.x, y: event.clientY - drag.current.y });
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
      >
        <div
          style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`, transformOrigin: "top left" }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </figure>
  );
}

function MarkdownBody({ content }: { content: string }) {
  const parts = content.split(/```mermaid\n([\s\S]*?)```/g);
  return (
    <div className="markdown">
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <MermaidBlock key={`diagram-${index}`} code={part.trim()} />
        ) : (
          <ReactMarkdown key={`md-${index}`} remarkPlugins={[remarkGfm]}>
            {part}
          </ReactMarkdown>
        ),
      )}
    </div>
  );
}

function HitlEditForm({ request }: { request: HitlRequestUI }) {
  const markHitlDecided = useWorkspaceStore((state) => state.markHitlDecided);
  const clearHitlEditor = useWorkspaceStore((state) => state.clearHitlEditor);
  const [draft, setDraft] = useState(JSON.stringify(request.proposed_payload, null, 2));
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      className="hitl-editor"
      onSubmit={(event) => {
        event.preventDefault();
        let parsed: Record<string, unknown>;
        try {
          const value = JSON.parse(draft) as unknown;
          if (value === null || typeof value !== "object" || Array.isArray(value)) {
            throw new Error("參數必須是物件");
          }
          parsed = value as Record<string, unknown>;
        } catch (caught) {
          setError(caught instanceof Error ? caught.message : "參數不是合法的 JSON。");
          return;
        }
        void decideHitl(request.hitl_request_id, { status: "MODIFIED", user_modified_payload: parsed })
          .then(() => markHitlDecided(request.hitl_request_id))
          .catch((caught: unknown) => {
            setError(caught instanceof Error ? caught.message : "無法送出修改後的參數。");
          });
      }}
    >
      <h2>修改後再執行 {request.tool_name}</h2>
      <textarea value={draft} onChange={(event) => setDraft(event.target.value)} rows={8} />
      {error ? <p className="error">{error}</p> : null}
      <div className="hitl-actions">
        <button type="submit" className="quiet-action">
          用修改後的參數執行
        </button>
        <button type="button" className="quiet-action" onClick={clearHitlEditor}>
          取消
        </button>
      </div>
    </form>
  );
}

function FileDiffPanel() {
  const diff = useWorkspaceStore((state) => state.pendingLocalDiff);
  const setPendingOriginal = useWorkspaceStore((state) => state.setPendingOriginal);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!diff?.handleKey || diff.originalContent) return;
    let cancelled = false;
    void BrowserLocalFsBridge.readFileForAgent(diff.handleKey, diff.relativePath)
      .then((file) => {
        if (!cancelled && file.encoding === "utf-8") setPendingOriginal(file.content);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [diff?.handleKey, diff?.originalContent, diff?.relativePath, setPendingOriginal]);

  if (!diff) {
    return <p className="empty">本機寫入的紅綠差異會在代理提出寫入後出現。確認前不會寫入磁碟。</p>;
  }

  return (
    <div className="file-diff">
      <h2>{diff.relativePath || "本機檔案"}</h2>
      <p className="note">左側是目前磁碟內容，右側是即將寫入的內容。按下確認後才會寫入本機硬碟。</p>
      <ReactDiffViewer
        oldValue={diff.originalContent}
        newValue={diff.proposedContent}
        splitView
        leftTitle="目前磁碟內容"
        rightTitle="即將寫入"
      />
      {error ? <p className="error">{error}</p> : null}
      <div className="hitl-actions">
        <button
          type="button"
          className="quiet-action"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setError(null);
            void confirmDiskWrite(diff)
              .catch((caught: unknown) => {
                setError(caught instanceof Error ? caught.message : "無法寫入本機檔案。");
                setBusy(false);
              });
          }}
        >
          確認寫入本機硬碟
        </button>
        <button
          type="button"
          className="quiet-action"
          disabled={busy}
          onClick={() => {
            void cancelDiskWrite(diff).catch((caught: unknown) => {
              setError(caught instanceof Error ? caught.message : "無法取消寫入。");
            });
          }}
        >
          取消
        </button>
      </div>
    </div>
  );
}

export function ArtifactWorkbench() {
  const hitlEditor = useWorkspaceStore((state) => state.hitlEditor);
  const activeRightTab = useWorkspaceStore((state) => state.activeRightTab);
  const setRightTab = useWorkspaceStore((state) => state.setRightTab);
  const artifacts = useWorkspaceStore((state) => state.artifacts);
  const selectedArtifactId = useWorkspaceStore((state) => state.selectedArtifactId);
  const dagSteps = useWorkspaceStore((state) => state.dagSteps);
  const mountedFolders = useWorkspaceStore((state) => state.mountedFolders);
  const openPendingLocalDiff = useWorkspaceStore((state) => state.openPendingLocalDiff);
  const selected = artifacts.find((item) => item.artifact_id === selectedArtifactId) ?? artifacts[0];
  const connected = mountedFolders.find((folder) => folder.isConnected);
  const [width, setWidth] = useState(42);

  function download() {
    if (!selected) return;
    const blob = new Blob([selected.content_body], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${selected.title || "artifact"}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="workbench" aria-label="右側工作台" style={{ width: `${width}%` }}>
      {hitlEditor ? <HitlEditForm request={hitlEditor} /> : null}
      <div className="tabs">
        <div role="tablist" aria-label="工作台分頁" style={{ display: "flex", gap: 6 }}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className="tab"
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={activeRightTab === tab.id}
            aria-controls={`panel-${tab.id}`}
            onClick={() => setRightTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
        </div>
        <button type="button" className="tab" onClick={() => setWidth((value) => Math.max(28, value - 4))}>
          縮窄
        </button>
        <button type="button" className="tab" onClick={() => setWidth((value) => Math.min(62, value + 4))}>
          加寬
        </button>
      </div>
      <div
        className="workbench-body"
        role="tabpanel"
        id={`panel-${activeRightTab}`}
        aria-labelledby={`tab-${activeRightTab}`}
      >
        {activeRightTab === "ARTIFACT" ? (
          selected ? (
            <>
              <h2>{selected.title}</h2>
              <p className="note">
                {selected.producer_role} · {selected.artifact_type}
              </p>
              <MarkdownBody content={selected.content_body} />
            </>
          ) : (
            <p className="empty">還沒有交付物。角色完成工單後，完整內容會出現在這裡。</p>
          )
        ) : null}
        {activeRightTab === "LIVE_DAG" ? (
          dagSteps.length === 0 ? (
            <p className="empty">主代理還沒有拆出工單。</p>
          ) : (
            <ol>
              {dagSteps.map((step) => (
                <li key={step.step_id}>
                  {step.step_id}. {step.target_role_code} {step.task_title}
                  {step.depends_on_steps.length > 0 ? `（依賴 ${step.depends_on_steps.join("、")}）` : ""}
                </li>
              ))}
            </ol>
          )
        ) : null}
        {activeRightTab === "FILE_DIFF" ? <FileDiffPanel /> : null}
        {activeRightTab === "TERMINAL_CLI" ? <p className="empty">技能的終端機輸出會在沙盒執行完成後出現。</p> : null}
        {activeRightTab === "PROMPT_INSPECTOR" ? <p className="empty">洋蔥式提示詞檢視會在規範編譯完成後出現。</p> : null}
      </div>
      {activeRightTab === "ARTIFACT" && selected ? (
        <div className="workbench-footer">
          <button type="button" onClick={download}>
            匯出 .md
          </button>
          <button
            type="button"
            disabled={!connected}
            onClick={() => {
              if (!selected || !connected) return;
              const safeName = `${selected.title || "artifact"}.md`.replace(/[\\/]/g, "-");
              openPendingLocalDiff({
                rpc_id: `artifact-${selected.artifact_id}`,
                handleKey: connected.handleKey,
                relativePath: safeName,
                originalContent: "",
                proposedContent: selected.content_body,
                executingRole: selected.producer_role,
              });
            }}
          >
            直接寫入本機掛載資料夾
          </button>
          <p className="note">
            {connected ? "會先打開紅綠差異，確認後才寫入磁碟。" : "尚未掛載本機資料夾，所以不能寫入磁碟。"}
          </p>
        </div>
      ) : null}
    </section>
  );
}

"use client";

import { Building2, Menu, MessageSquare, Moon, PanelRight, Plug, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { ArtifactWorkbench } from "@/components/ArtifactViewer";
import { useWorkspaceStore } from "@/lib/store/useWorkspaceStore";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const sessionTitle = useWorkspaceStore((state) => state.sessionTitle);
  const hitlCount = useWorkspaceStore((state) => state.hitlRequests.filter((item) => item.status === "PENDING").length);
  const liveAnnouncement = useWorkspaceStore((state) => state.liveAnnouncement);
  const isRightPaneOpen = useWorkspaceStore((state) => state.isRightPaneOpen);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [navOpen, setNavOpen] = useState(false);
  const [benchOpen, setBenchOpen] = useState(false);
  const [narrow, setNarrow] = useState(false);
  const isChat = pathname.startsWith("/chat");

  useEffect(() => {
    const media = window.matchMedia("(max-width: 960px)");
    const apply = () => setNarrow(media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setNavOpen(false);
      setBenchOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const stored = window.localStorage.getItem("eamp-theme");
    const next = stored === "dark" || stored === "light" ? stored : "light";
    setTheme(next);
    document.documentElement.classList.toggle("dark", next === "dark");
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.classList.toggle("dark", next === "dark");
    window.localStorage.setItem("eamp-theme", next);
  }

  const nav = (
    <nav aria-label="主要">
      <Link className="nav-link" href="/chat" aria-current={isChat ? "page" : undefined} onClick={() => setNavOpen(false)}>
        <MessageSquare size={18} aria-hidden="true" /> 協作區
      </Link>
      <Link
        className="nav-link"
        href="/org-chart"
        aria-current={pathname.startsWith("/org-chart") ? "page" : undefined}
        onClick={() => setNavOpen(false)}
      >
        <Building2 size={18} aria-hidden="true" /> 組織圖與看板
      </Link>
      <button type="button" className="nav-link" aria-disabled="true" disabled>
        產出物中心（稍後提供）
      </button>
      <Link
        className="nav-link"
        href="/studio"
        aria-current={pathname.startsWith("/studio") ? "page" : undefined}
        onClick={() => setNavOpen(false)}
      >
        自建工作坊
      </Link>
      <Link
        className="nav-link"
        href="/connectors"
        aria-current={pathname.startsWith("/connectors") ? "page" : undefined}
        onClick={() => setNavOpen(false)}
      >
        <Plug size={18} aria-hidden="true" /> 工具與連接器
      </Link>
    </nav>
  );

  return (
    <div className="shell">
      <a className="skip" href="#main">
        跳至主要內容
      </a>
      <header className="topbar">
        <button type="button" className="icon-button mobile-only" aria-label="開啟導覽" onClick={() => setNavOpen(true)}>
          <Menu size={18} aria-hidden="true" />
        </button>
        <div className="brand-lockup">
          <span className="mark" aria-hidden="true">
            E
          </span>
          <div className="brand-copy">
            <Link className="brand" href="/chat">
              Enterprise Agent Hub
            </Link>
            <p className="session-title">{sessionTitle}</p>
          </div>
        </div>
        <div className="top-meta">
          <span className="chip quiet">
            <span className="dot" aria-hidden="true" />
            本機掛載 0
          </span>
          <span className="chip">待審批 {hitlCount}</span>
          <button type="button" className="ghost" onClick={toggleTheme}>
            {theme === "dark" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
            {theme === "dark" ? "淺色" : "深色"}
          </button>
          {isChat ? (
            <button type="button" className="icon-button mobile-only" aria-label="開啟工作台" onClick={() => setBenchOpen(true)}>
              <PanelRight size={18} aria-hidden="true" />
            </button>
          ) : null}
        </div>
      </header>
      <div className="frame">
        <aside className="rail">{nav}</aside>
        <div className="stage" id="main">
          {children}
        </div>
        {isChat && isRightPaneOpen && !narrow ? <ArtifactWorkbench /> : null}
      </div>
      <div className="live" aria-live="polite">
        {liveAnnouncement}
      </div>
      {navOpen ? (
        <>
          <button type="button" className="drawer-backdrop" aria-label="關閉導覽" onClick={() => setNavOpen(false)} />
          <div className="sheet left" role="dialog" aria-modal="true" aria-label="導覽">
            <button type="button" className="ghost" onClick={() => setNavOpen(false)} autoFocus>
              關閉
            </button>
            {nav}
          </div>
        </>
      ) : null}
      {benchOpen && isChat ? (
        <>
          <button type="button" className="drawer-backdrop" aria-label="關閉工作台" onClick={() => setBenchOpen(false)} />
          <div className="sheet bottom" role="dialog" aria-modal="true" aria-label="工作台">
            <button type="button" className="ghost" onClick={() => setBenchOpen(false)} autoFocus>
              關閉工作台
            </button>
            <ArtifactWorkbench />
          </div>
        </>
      ) : null}
    </div>
  );
}

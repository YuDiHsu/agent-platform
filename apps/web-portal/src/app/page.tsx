"use client";

import { useCallback, useEffect, useState } from "react";

type SeedCounts = {
  roles: number;
  rules: number;
  skills: number;
};

type HealthResponse = {
  status: "ok" | "degraded";
  postgres: "ok" | "error";
  redis: "ok" | "error";
  seed: SeedCounts | null;
};

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function label(value: "ok" | "error" | undefined, disconnected: boolean): string {
  if (value === "ok") return "正常";
  if (value === "error" || disconnected) return "無法連線";
  return "讀取中";
}

export default function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/health`);
      if (!response.ok) throw new Error(`健康檢查回應 ${response.status}`);
      setHealth((await response.json()) as HealthResponse);
    } catch (caught) {
      setHealth(null);
      setError(caught instanceof Error && caught.message.startsWith("健康檢查回應") ? caught.message : "無法連線至 API");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const seedText = health?.seed
    ? `${health.seed.roles} 個角色、${health.seed.rules} 條規範、${health.seed.skills} 項技能`
    : "尚無種子資料";

  return (
    <div className="stage-scroll">
      <div className="health-page">
        <h1>企業多代理協作平台</h1>
        <p className="note">這裡確認基礎設施、資料庫與內建種子。協作請從左側進入協作區。</p>
        <section className="panel" aria-live="polite">
          <ul className="status-list">
            <li>
              <span>整體狀態</span>
              <strong className={health?.status === "ok" ? "ok" : "error"}>
                {error ? "無法連線" : health?.status === "ok" ? "可提供服務" : loading ? "讀取中" : "尚未就緒"}
              </strong>
            </li>
            <li>
              <span>PostgreSQL</span>
              <strong className={health?.postgres === "ok" ? "ok" : "error"}>{label(health?.postgres, error !== null)}</strong>
            </li>
            <li>
              <span>Redis</span>
              <strong className={health?.redis === "ok" ? "ok" : "error"}>{label(health?.redis, error !== null)}</strong>
            </li>
            <li>
              <span>內建種子</span>
              <strong>{error ? "無法讀取" : seedText}</strong>
            </li>
          </ul>
          {error ? <p className="error">{error}</p> : null}
          <button className="text-button primary" type="button" onClick={() => void refresh()} disabled={loading}>
            {loading ? "檢查中" : "重新檢查"}
          </button>
        </section>
      </div>
    </div>
  );
}

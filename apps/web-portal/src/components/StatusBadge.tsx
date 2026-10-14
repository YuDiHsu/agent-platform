import {
  Ban,
  CheckCircle2,
  Circle,
  CircleAlert,
  LoaderCircle,
  MonitorSmartphone,
  ShieldAlert,
  XCircle,
} from "lucide-react";

const LABELS: Record<string, string> = {
  PENDING: "等待",
  IN_PROGRESS: "執行中",
  WAITING_HITL: "待審批",
  WAITING_BROWSER: "等待瀏覽器",
  PAUSED_QUOTA_EXCEEDED: "額度暫停",
  COMPLETED: "已完成",
  FAILED: "失敗",
  CIRCUIT_BROKEN: "已中止",
};

const CLASS_NAMES: Record<string, string> = {
  PENDING: "status-pending",
  IN_PROGRESS: "status-progress",
  WAITING_HITL: "status-hitl",
  WAITING_BROWSER: "status-browser",
  PAUSED_QUOTA_EXCEEDED: "status-quota",
  COMPLETED: "status-done",
  FAILED: "status-failed",
  CIRCUIT_BROKEN: "status-circuit",
};

export function statusLabel(status: string): string {
  return LABELS[status] ?? status;
}

export function StatusBadge({ status }: { status: string }) {
  const label = statusLabel(status);
  const className = CLASS_NAMES[status] ?? "status-pending";
  const icon =
    status === "COMPLETED" ? (
      <CheckCircle2 size={16} aria-hidden="true" />
    ) : status === "IN_PROGRESS" ? (
      <LoaderCircle size={16} className="pulse" aria-hidden="true" />
    ) : status === "WAITING_HITL" ? (
      <ShieldAlert size={16} aria-hidden="true" />
    ) : status === "WAITING_BROWSER" ? (
      <MonitorSmartphone size={16} aria-hidden="true" />
    ) : status === "FAILED" || status === "PAUSED_QUOTA_EXCEEDED" ? (
      <CircleAlert size={16} aria-hidden="true" />
    ) : status === "CIRCUIT_BROKEN" ? (
      <Ban size={16} aria-hidden="true" />
    ) : status === "PENDING" ? (
      <Circle size={16} aria-hidden="true" />
    ) : (
      <XCircle size={16} aria-hidden="true" />
    );
  return (
    <span className={`badge ${className}`}>
      {icon}
      {label}
    </span>
  );
}

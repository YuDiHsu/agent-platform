"use client";

import { ChevronRight } from "lucide-react";

import { StatusBadge } from "@/components/StatusBadge";
import { useWorkspaceStore } from "@/lib/store/useWorkspaceStore";

export function MiniDagProgressBar() {
  const steps = useWorkspaceStore((state) => state.dagSteps);
  if (steps.length === 0) return null;
  return (
    <ol className="mini-dag" aria-label="DAG 進度">
      {steps.map((step, index) => (
        <li key={step.step_id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {index > 0 ? <ChevronRight className="dag-arrow" size={16} aria-hidden="true" /> : null}
          <span className="dag-pill status-pending">
            <span>
              {step.step_id}. {step.target_role_code} {step.task_title}
            </span>
            <StatusBadge status={step.status} />
          </span>
        </li>
      ))}
    </ol>
  );
}

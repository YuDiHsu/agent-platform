"use client";

import type { CatalogRule } from "@/lib/api";

export function RuleBindingSelector({
  rules,
  selected,
  onToggle,
}: {
  rules: CatalogRule[];
  selected: string[];
  onToggle: (code: string) => void;
}) {
  const mandatory = rules.filter((rule) => rule.scope_type === "GLOBAL_MANDATORY");
  const exclusive = rules.filter((rule) => rule.scope_type === "ROLE_EXCLUSIVE");
  return (
    <fieldset className="studio-block">
      <legend>規範綁定</legend>
      <ul className="chip-list">
        {mandatory.map((rule) => (
          <li key={rule.code}>
            <span className="locked-chip">{rule.name}</span>
          </li>
        ))}
      </ul>
      {exclusive.map((rule) => (
        <label key={rule.code} className="check-row">
          <input
            type="checkbox"
            checked={selected.includes(rule.code)}
            onChange={() => onToggle(rule.code)}
          />
          {rule.name}
        </label>
      ))}
    </fieldset>
  );
}

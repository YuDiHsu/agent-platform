"use client";

import type { PromptLayer } from "@/lib/api";

const LAYER_LABEL: Record<number, string> = {
  1: "Layer 1 全公司與部門規範",
  2: "Layer 2 角色職責",
  3: "Layer 3 角色專屬規範",
  4: "Layer 4 技能清單",
  5: "Layer 5 已啟用 SOP",
  6: "Layer 6 本回合工具",
};

export function OnionInspector({ layers, prompt }: { layers: PromptLayer[]; prompt: string }) {
  return (
    <section className="studio-block" aria-label="洋蔥式提示詞檢視器">
      <h2>洋蔥式 Prompt</h2>
      {layers.map((layer) => (
        <article key={`${layer.layer}-${layer.heading}`} className={`onion-layer layer-${layer.layer}`}>
          <h3>{LAYER_LABEL[layer.layer] ?? `Layer ${layer.layer}`}</h3>
          <p>{layer.heading}</p>
          <pre>{layer.body}</pre>
        </article>
      ))}
      <h3>合併預覽</h3>
      <pre className="onion-full">{prompt}</pre>
    </section>
  );
}

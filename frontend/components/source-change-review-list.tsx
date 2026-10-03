"use client";

import { useState } from "react";
import { apiBase } from "@/lib/api";

export type SourceChange = {
  id: number;
  endpoint_id: string;
  document_version_id: string;
  risk_level: string;
  status: string;
  summary: string;
  created_at: string;
};

export function SourceChangeReviewList({ initial }: { initial: SourceChange[] }) {
  const [items, setItems] = useState(initial);
  const [message, setMessage] = useState("");
  async function act(id: number, action: "approve" | "reject" | "acknowledge") {
    setMessage("");
    const response = await fetch(`${apiBase}/v1/admin/intake/change-reviews/${id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, note: "管理员在变化审核页处理" }),
    });
    const data = await response.json();
    if (!response.ok) { setMessage(typeof data.detail === "string" ? data.detail : "处理失败"); return; }
    setItems(current => current.filter(item => item.id !== id));
  }
  return <div>{message && <p role="alert">{message}</p>}{items.map(item => <article className="card" key={item.id}>
    <h2>{item.summary}</h2><p>风险：{item.risk_level} · {new Date(item.created_at).toLocaleString("zh-CN")}</p>
    <a href={`/admin/intake-document/${item.document_version_id}`}>查看版本与差异</a>
    <div className="actions"><button onClick={() => act(item.id, "approve")}>确认变化</button><button onClick={() => act(item.id, "acknowledge")}>已知悉待后续</button><button className="danger" onClick={() => act(item.id, "reject")}>拒绝本次变化</button></div>
  </article>)}{!items.length && <p>当前没有待处理的来源变化。</p>}</div>;
}

"use client";

import { useState } from "react";
import { apiBase } from "@/lib/api";

export type SourceCandidate = {
  id: string;
  document_version_id: string;
  source_code: string;
  name: string;
  region_code: string;
  base_url: string;
  authority_level: string;
  created_at: string;
};

export function SourceCandidateReviewList({ initial }: { initial: SourceCandidate[] }) {
  const [items, setItems] = useState(initial);
  const [message, setMessage] = useState("");
  async function act(id: string, action: "approve" | "reject") {
    setMessage("");
    const response = await fetch(`${apiBase}/v1/admin/intake/source-candidates/${id}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, note: "管理员核验地方招聘平台目录候选" }),
    });
    const data = await response.json();
    if (!response.ok) {
      setMessage(typeof data.detail === "string" ? data.detail : "处理失败");
      return;
    }
    setItems(current => current.filter(item => item.id !== id));
    setMessage(action === "approve" ? "已生成未启用来源；启用前仍需核对栏目、robots 和条款。" : "已拒绝来源候选。");
  }
  return <div>
    {message && <p role="status">{message}</p>}
    {items.map(item => <article className="card" key={item.id}>
      <p className="eyebrow">{item.source_code} · {item.region_code}</p>
      <h2>{item.name}</h2>
      <p>权威等级 {item.authority_level} · 发现时间 {new Date(item.created_at).toLocaleString("zh-CN")}</p>
      <p><a href={item.base_url} target="_blank" rel="noreferrer">核对候选官方入口</a> · <a href={`/admin/intake-document/${item.document_version_id}`}>查看目录原文证据</a></p>
      <div className="actions">
        <button onClick={() => act(item.id, "approve")}>批准为未启用来源</button>
        <button className="danger" onClick={() => act(item.id, "reject")}>拒绝候选</button>
      </div>
    </article>)}
    {!items.length && <p>当前没有待审核的地方来源候选。</p>}
  </div>;
}

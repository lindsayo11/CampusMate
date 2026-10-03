"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { apiBase } from "@/lib/api";
type Source = { id: string; source_url: string; fetched_at: string; content_hash: string; previous_id: string | null };
export default function Sources() {
  const [items, setItems] = useState<Source[]>([]), [raw, setRaw] = useState(""), [payload, setPayload] = useState(""), [message, setMessage] = useState("");
  const [detail, setDetail] = useState<{ id:string; raw_text: string; diff: string; reviews: number[] } | null>(null), [busy, setBusy] = useState(false);
  async function load() { const r = await fetch(apiBase + "/v1/admin/sources"); if (!r.ok) throw Error("加载失败，请确认管理员权限"); setItems(await r.json()); }
  useEffect(() => { load().catch(e => setMessage(e.message)); }, []);
  return <div className="shell page"><h1>来源归档与导入</h1><p>粘贴获准使用的公开原文及结构化字段。原文以 SHA-256 记录版本；导入后进入人工审核，不自动发布。</p><Link href="/admin/review">前往审核队列</Link><form className="form-card" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setMessage("");
    try {
      const data = JSON.parse(payload);
      const r = await fetch(apiBase + "/v1/admin/sources/import", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ raw_text: raw, payload: data }) });
      const result = await r.json();
      if (!r.ok) throw Error(typeof result.detail === "string" ? result.detail : "字段校验失败，请检查必填项、日期时区及规则原文引用");
      setMessage(result.duplicate ? `内容已导入，审核编号 ${result.review_id}` : `归档成功，审核编号 ${result.review_id}`); await load();
    } catch (e) { setMessage(e instanceof SyntaxError ? "结构化字段不是有效 JSON" : (e as Error).message); } finally { setBusy(false); }
  }}><label>公开原文<textarea required minLength={20} maxLength={200000} rows={8} value={raw} onChange={e => setRaw(e.target.value)} /></label><label>结构化字段 JSON<textarea required rows={12} value={payload} onChange={e => setPayload(e.target.value)} /></label><p>必填：type、title、organization、summary、location、deadline、source_url、source_label、fetched_at。日期带时区；tags 为数组。可选 rules 支持 school、college、grade、major，规则 evidence 必须为原文片段。完整示例见源码 docs/CONTENT_INTAKE.md。</p><button disabled={busy}>{busy ? "导入中…" : "归档并提交审核"}</button></form><p role="status">{message}</p><h2>最近归档</h2>{items.length === 0 && <p>暂无归档。</p>}{items.map(item => <article className="card" key={item.id}><a href={item.source_url} target="_blank" rel="noreferrer">{item.source_url}</a><p>{new Date(item.fetched_at).toLocaleString("zh-CN")} · {item.previous_id ? "变更版本" : "首个版本"}</p><code style={{ overflowWrap: "anywhere" }}>{item.content_hash}</code><button onClick={async () => { try { const r = await fetch(`${apiBase}/v1/admin/sources/${item.id}`); if (!r.ok) throw Error("读取归档失败"); setDetail(await r.json()); } catch (e) { setMessage((e as Error).message); } }}>查看原文与差异</button></article>)}{detail && <section><h2>归档原文</h2><p>公开检索会展示这份原文的片段。请先核对整篇内容的公开权限，确保无个人隐私或不宜公开内容，并通过关联机会审核。</p>{[true,false].map(visible=><button key={String(visible)} disabled={busy} onClick={async()=>{if(visible&&!window.confirm("已核对整篇原文可以公开检索，确认开放？"))return;setBusy(true);try{const r=await fetch(`${apiBase}/v1/admin/knowledge/documents/${detail.id}/access`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({public:visible})});const data=await r.json();if(!r.ok)throw Error(data.detail);setMessage(visible?"已允许公开检索原文":"已关闭原文公开检索")}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}}>{visible?"允许公开检索原文":"关闭公开检索"}</button>)}<pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{detail.raw_text}</pre><h2>与前一版本的差异</h2><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{detail.diff || "无变化"}</pre><p>关联审核：{detail.reviews.join("、")}</p></section>}</div>;
}

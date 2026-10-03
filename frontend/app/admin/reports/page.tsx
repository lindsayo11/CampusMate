"use client";
import { useEffect, useState } from "react";
import { apiBase } from "@/lib/api";
type Report = { id: number; reason: string; status: string; decision_note: string | null; evidence: { body: string; sender: string } | null };
export default function Reports() {
  const [items, setItems] = useState<Report[]>([]), [status, setStatus] = useState("pending"), [message, setMessage] = useState("");
  const [notes, setNotes] = useState<Record<number, string>>({}), [busy, setBusy] = useState(false);
  async function load() {
    const r = await fetch(`${apiBase}/v1/admin/reports?status=${status}`, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status === 403 ? "需要管理员权限" : r.status === 401 ? "请先登录" : "加载失败");
    setItems((await r.json()).items);
  }
  useEffect(() => { setItems([]); load().catch(e => setMessage(e.message)); }, [status]);
  async function decide(id: number, action: string) {
    setBusy(true); setMessage("");
    try {
      const r = await fetch(`${apiBase}/v1/admin/reports/${id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, note: notes[id] || "" }) });
      if (!r.ok) { const data = await r.json(); throw new Error(typeof data.detail === "string" ? data.detail : "请填写处理理由"); }
      await load(); setMessage("处理结果已保存并留存审计");
    } catch (e) { setMessage((e as Error).message); } finally { setBusy(false); }
  }
  return <div className="shell page"><h1>举报处理</h1><p>仅展示被举报消息作为审核依据。移除后普通用户只能看到占位提示，原始证据保留。</p><label>处理状态<select value={status} onChange={e => { setMessage(""); setStatus(e.target.value); }}><option value="pending">待处理</option><option value="removed">已移除</option><option value="dismissed">已驳回</option></select></label>{items.length === 0 && <p>此状态暂无举报。</p>}{items.map(item => <article className="form-card" key={item.id}><h2>举报 #{item.id}</h2><p>原因：{item.reason}</p><p>被举报消息：{item.evidence?.body || "证据不可用"}</p>{status === "pending" ? <><label>处理理由<textarea maxLength={1000} value={notes[item.id] || ""} onChange={e => setNotes({ ...notes, [item.id]: e.target.value })} /></label><button disabled={busy || !notes[item.id]?.trim()} onClick={() => decide(item.id, "remove")}>移除消息</button><button disabled={busy || !notes[item.id]?.trim()} onClick={() => decide(item.id, "dismiss")}>驳回举报</button></> : <p>处理说明：{item.decision_note}</p>}</article>)}<p role="status">{message}</p></div>;
}

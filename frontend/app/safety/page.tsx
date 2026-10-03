"use client";
import { useEffect, useState } from "react";
import { apiBase } from "@/lib/api";
import {PageHeading,TopicBar} from "@/components/ui";
type Report = { id: number; reason: string; status: string };
export default function Safety() {
  const [blocks, setBlocks] = useState<{ target: string }[]>([]), [reports, setReports] = useState<Report[]>([]), [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true), [loaded, setLoaded] = useState(false);
  async function load() {
    setLoading(true);
    try {
    const [b, r] = await Promise.all([fetch(apiBase + "/v1/blocks"), fetch(apiBase + "/v1/reports/mine")]);
    if (!b.ok || !r.ok) throw Error("加载失败，请确认已登录");
    setBlocks(await b.json()); setReports(await r.json()); setLoaded(true);
    } finally { setLoading(false); }
  }
  useEffect(() => { load().catch(e => setMessage(e.message)); }, []);
  return <div className="shell page narrow"><PageHeading eyebrow="PRIVACY & ACCOUNT" title="隐私与安全" description="管理联系边界，查看你提交的举报处理结果。"/><section className="topic-section"><TopicBar title="用户与管理员的权限"/><div className="path-overview"><p>普通用户管理自己的资料、计划、提醒和会话；团队成员仅访问已加入的房间。队长负责邀请成员和分配任务。</p><p>管理员通过独立运营后台处理数据源、发布、审核、平台内容删除和举报。管理员进入学生视图时，仍只查看当前账号的个人记录。</p><p>演示模式包含模拟账号与测试批次，用于操作演示。批次标识保留在信息详情中；演示数据与实际运营数据应分别管理。</p></div></section>{loading && <p role="status">正在加载安全记录…</p>}<h2>已拉黑用户</h2>{loaded && !loading && blocks.length === 0 && <p>暂无拉黑记录。</p>}{blocks.map(b => <article key={b.target}><span>{b.target} </span><button onClick={async () => { try { const r = await fetch(`${apiBase}/v1/blocks/${encodeURIComponent(b.target)}`, { method: "DELETE" }); if (!r.ok) throw Error("解除失败"); await load(); setMessage("已解除拉黑"); } catch (e) { setMessage((e as Error).message); } }}>解除拉黑</button></article>)}<h2>我的举报</h2>{loaded && !loading && reports.length === 0 && <p>暂无举报记录。</p>}{reports.map(r => <article className="card" key={r.id}><p>{r.reason}</p><p>{{ pending: "等待审核", dismissed: "已驳回", removed: "已处理并移除消息" }[r.status] || r.status}</p></article>)}<p role="status">{message}</p>{!loading && !loaded && <button onClick={() => { setMessage(""); void load().catch(e => setMessage(e.message)); }}>重试加载</button>}</div>;
}

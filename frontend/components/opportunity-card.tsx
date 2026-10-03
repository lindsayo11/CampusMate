import Link from "next/link";
import type { Opportunity } from "@/lib/api";
const labels: Record<string,string> = {job:"就业",contest:"竞赛",civil_service:"考公",volunteer:"志愿",club:"社团",graduate:"升学"};
export function OpportunityCard({item}:{item:Opportunity}) { return <article className="card opportunity-card"><div className="cardtop"><span className="type">{labels[item.type]||item.type}</span><span className="trust">请核对原文</span></div><h3><Link href={`/opportunity/${item.id}`}>{item.title}</Link></h3><p className="org">{item.organization} · {item.location}</p><p className="summary">{item.summary}</p><div className="tagrow">{item.tags.slice(0,3).map(t=><span key={t}>{t}</span>)}</div><footer><span>截止 {new Date(item.deadline).toLocaleDateString("zh-CN")}</span><Link href={`/opportunity/${item.id}`}>查看详情 →</Link></footer></article>; }


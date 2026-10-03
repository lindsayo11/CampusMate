"use client";
import { useState } from "react";
import { apiBase, Eligibility } from "@/lib/api";
type Option = { id: string; title: string };
export function EligibilityPanel({ opportunities, initialId }: { opportunities: Option[]; initialId?:string }) {
  const [selected, setSelected] = useState(opportunities.some(x=>x.id===initialId)?initialId!:opportunities[0]?.id || ""), [result, setResult] = useState<Eligibility | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function check() {
    setBusy(true); setError(""); setResult(null);
    try {
      const r = await fetch(`${apiBase}/v1/tools/eligibility_check`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ opportunity_id: selected }) });
      const data = await r.json();
      if (!r.ok) throw Error(typeof data.detail === "string" ? data.detail : "判断失败，请稍后重试");
      setResult(data);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <section className="eligibility-card"><label>选择已发布机会<select value={selected} disabled={busy} onChange={e => { setSelected(e.target.value); setResult(null); }}>{opportunities.map(o => <option key={o.id} value={o.id}>{o.title}</option>)}</select></label>{!opportunities.length && <p>暂无已发布机会，请等待管理员导入并审核。</p>}<p>按已审核的规则逐项判断；没有规则或画像不完整时明确显示信息不足。</p><button onClick={check} disabled={busy || !selected}>{busy ? "正在判断…" : "使用我的画像判断"}</button>{error && <p role="alert">{error}</p>}{result && <div className={`verdict ${result.eligible ? "pass" : "fail"}`}><h3>{result.eligible === null ? "信息不足，暂时无法判断" : result.eligible ? "当前画像符合已录入条件，请核对官方原文" : "当前画像存在不符合项"}</h3>{!result.results.length&&<p>未找到依据：该机会暂无已审核资格规则，请核对官方原文。</p>}{result.results.map((x, i) => <div className="rule" key={i}><b>{x.passed === null ? "信息不足" : x.passed ? "通过" : "未通过"} · {x.label}</b><span>你的信息：{x.actual}｜要求：{x.expected}</span>{x.evidence && <blockquote>{x.evidence}</blockquote>}<a href={x.source_url}>查看规则来源</a></div>)}</div>}</section>;
}

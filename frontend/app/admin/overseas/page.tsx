import { privateApi } from "@/lib/session-api";
import { OverseasReviewControls } from "@/components/overseas-review-controls";

type Institution = {id:string;name:string;official_id:string|null;country_code:string;
  public_status:string;review_status:string;website_url:string;source_document_id:string|null};
type Program = {id:string;name:string;program_code:string;degree_level:string;public_status:string;review_status:string;
  official_url:string;source_document_id:string|null};
type Cycle = {id:string;cycle_year:number;deadline_at:string|null;status:string;review_status:string;
  requirements_source_type:string;source_document_id:string};
type Rule = {id:number;field:string;expected:string;review_status:string;evidence_id:string|null};
type Blocker = {id:string;blocker_type:string;detail:string;required_action:string;status:string};

export default async function OverseasReviewPage(){
  const [entities, cycles, queue] = await Promise.all([
    privateApi("/v1/admin/intake/overseas/institutions") as Promise<{institution:Institution;programs:Program[]}[]>,
    privateApi("/v1/admin/intake/overseas/cycles") as Promise<{cycle:Cycle;institution:Institution|null;program:Program|null;rules:Rule[]}[]>,
    privateApi("/v1/admin/intake/overseas/review-queue") as Promise<{registry_assertions:unknown[];blockers:Blocker[]}>,
  ]);
  return <div className="shell page">
    <p className="eyebrow">M5 国（境）外升学</p>
    <h1>实体、申请周期、规则与证据审核</h1>
    <p className="lead">Registry 仅证明实体和公共状态。年度申请条件必须来自大学第一方页面，审核前保持草稿或待核验。</p>
    <section className="card"><h2>真实阻塞</h2>
      {queue.blockers.length ? queue.blockers.map(item=><article key={item.id}>
        <strong>{item.blocker_type}</strong><p>{item.detail}</p><p>所需动作：{item.required_action||"人工复核"}</p>
      </article>) : <p>当前没有开放 Blocker。</p>}
    </section>
    <section><h2>境外院校与项目</h2>{entities.map(({institution,programs})=><article className="card" key={institution.id}>
      <h3>{institution.name} · {institution.country_code}</h3>
      <p>Registry ID：{institution.official_id||"待核验"} · 公共状态：{institution.public_status} · 审核：{institution.review_status}</p>
      {institution.website_url&&<a href={institution.website_url} target="_blank" rel="noreferrer">打开学校官网</a>}
      <OverseasReviewControls type="institution" id={institution.id}/>
      {programs.map(program=><div key={program.id}><strong>{program.name}</strong><p>{program.degree_level} · {program.public_status} · {program.program_code} · {program.review_status}</p><OverseasReviewControls type="program" id={program.id}/></div>)}
    </article>)}</section>
    <section><h2>年度申请周期与规则</h2>{cycles.map(({cycle,institution,program,rules})=><article className="card" key={cycle.id}>
      <h3>{cycle.cycle_year} · {institution?.name||"未知院校"} · {program?.name||"未知项目"}</h3>
      <p>截止：{cycle.deadline_at?new Date(cycle.deadline_at).toLocaleString("zh-CN"):"待核验"} · 来源层：{cycle.requirements_source_type} · 审核：{cycle.review_status}</p>
      {program?.official_url&&<a href={program.official_url} target="_blank" rel="noreferrer">打开大学第一方项目页</a>}
      <OverseasReviewControls type="cycle" id={cycle.id}/>
      <ul>{rules.map(rule=><li key={rule.id}><strong>{rule.field}</strong>：{rule.expected} · {rule.review_status} · Evidence {rule.evidence_id||"缺失"}</li>)}</ul>
    </article>)}</section>
  </div>;
}

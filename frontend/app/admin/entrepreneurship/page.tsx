import { privateApi } from "@/lib/session-api";
import { PolicyReviewControls } from "@/components/policy-review-controls";

type Policy={id:string;policy_code:string;title:string;publisher:string;jurisdiction_level:string;
  jurisdiction_path:string;effective_at:string|null;expires_at:string|null;application_url:string;
  review_status:string;source_document_id:string};
type Rule={id:number;field:string;expected:string;review_status:string;evidence_id:string|null};
type Relation={id:number;to_policy_id:string;relation_type:string;review_status:string;evidence_id:string|null};
type Blocker={id:string;blocker_type:string;detail:string;required_action:string;status:string};

export default async function EntrepreneurshipReviewPage(){
  const [records,queue]=await Promise.all([
    privateApi("/v1/admin/intake/entrepreneurship/policies") as Promise<{policy:Policy;rules:Rule[];relations:Relation[]}[]>,
    privateApi("/v1/admin/intake/entrepreneurship/review-queue") as Promise<{blockers:Blocker[]}>,
  ]);
  return <div className="shell page">
    <p className="eyebrow">M6 创业政策</p><h1>国家、省、市、区县与高校政策链审核</h1>
    <p className="lead">政策、资格规则、关系和证据均先进入待审核状态。API 密钥、登录、商业许可与个人业务页面只保留 Blocker。</p>
    <section className="card"><h2>真实阻塞</h2>{queue.blockers.length?queue.blockers.map(item=><article key={item.id}>
      <strong>{item.blocker_type}</strong><p>{item.detail}</p><p>所需动作：{item.required_action||"人工复核"}</p>
    </article>):<p>当前没有开放 Blocker。</p>}</section>
    <section><h2>政策链与资格规则</h2>{records.map(({policy,rules,relations})=><article className="card" key={policy.id}>
      <p className="eyebrow">{policy.jurisdiction_level} · {policy.policy_code}</p><h3>{policy.title}</h3>
      <p>{policy.publisher} · 审核：{policy.review_status} · 辖区链：{policy.jurisdiction_path}</p>
      {policy.application_url&&<a href={policy.application_url} target="_blank" rel="noreferrer">打开公开办理入口</a>}
      <p><a href={`/admin/intake-document/${policy.source_document_id}`}>查看 DocumentVersion、内容哈希与版本差异</a></p>
      <PolicyReviewControls id={policy.id}/>
      <h4>上位政策关系</h4><ul>{relations.length?relations.map(row=><li key={row.id}>{row.relation_type} → {row.to_policy_id} · {row.review_status} · Evidence {row.evidence_id||"缺失"}</li>):<li>国家级根政策</li>}</ul>
      <h4>规则</h4><ul>{rules.map(rule=><li key={rule.id}><strong>{rule.field}</strong>：{rule.expected} · {rule.review_status} · Evidence {rule.evidence_id||"缺失"}</li>)}</ul>
    </article>)}</section>
  </div>;
}

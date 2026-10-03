"use client";
import { useState } from "react";
import { apiBase } from "@/lib/api";

type Doc = {id:string;canonical_url:string;version_no:number;import_mode:string;test_batch:string|null;deleted_at:string|null;publication:null|{
  id:string;status:string;first_reviewed_by:string|null;submitted_by:string}};
type Inspection = {ready:boolean;blockers:string[];relation_reviews:{id:number;to_policy_id:string;relation_type:string;review_status:string}[];snapshot:{
  rules:{id:number;field:string;expected:string;evidence_id:string}[];
  relations:{id:number;relation_type:string}[];
  evidence:{id:string;evidence_location:string;quote_or_normalized_fact:string}[];
  items:{id:string;title:string}[];
}};

export function DataConsole({documents}:{documents:Doc[]}) {
  const [selected,setSelected]=useState<Doc|null>(null);
  const [inspection,setInspection]=useState<Inspection|null>(null);
  const [message,setMessage]=useState("");
  const [busy,setBusy]=useState(false);
  async function api(path:string,method="GET",body?:unknown) {
    const r=await fetch(apiBase+path,{method,headers:{"Content-Type":"application/json"},
      ...(body?{body:JSON.stringify(body)}:{})});
    const data=await r.json();
    if(!r.ok)throw Error(typeof data.detail==="string"?data.detail:JSON.stringify(data.detail));
    return data;
  }
  async function inspect(doc:Doc) {
    setSelected(doc);setInspection(null);setMessage("");
    try {setInspection(await api(`/v1/admin/data/documents/${doc.id}`));}
    catch(e){setMessage((e as Error).message);}
  }
  async function mutate(path:string,method:string,body:unknown) {
    if(busy)return;setBusy(true);setMessage("");
    try {await api(path,method,body);window.location.reload();}
    catch(e){setMessage((e as Error).message);}
    finally{setBusy(false);}
  }
  function publish(action:"submit"|"approve"|"reject"|"withdraw") {
    if(!selected)return;
    const note=window.prompt("填写核对原始文件、关键字段及本次操作的依据（不少于3字）");
    if(!note)return;
    if(!window.confirm("已核对原始文件与证据；明确不是测试样例。继续？"))return;
    if(action==="submit")void mutate(`/v1/admin/data/documents/${selected.id}/submit`,"POST",{note,verified_original:true});
    else if(selected.publication)void mutate(`/v1/admin/data/publications/${selected.publication.id}`,"PATCH",{action,note,verified_original:true});
  }
  return <section><h2>系统直接入库 · 手动导入审核</h2>
    <button disabled={busy} onClick={()=>mutate('/v1/admin/data/publish-system','POST',{})}>发布已有系统导入记录</button>
    {documents.length===0&&<p>尚未导入文档。上传匿名公开的官方原始文件后开始审核。</p>}
    {documents.map(d=><article className="card" key={d.id}><p>版本 {d.version_no} · {d.import_mode} · {d.publication?.status||"未提交"} {d.deleted_at?'· 已删除':''}</p>
      {d.test_batch&&<p>测试批次：{d.test_batch}</p>}
      <button disabled={busy||!!d.deleted_at} onClick={()=>{if(window.confirm('删除此内容并停止公开展示？个人计划保留，订阅会收到变更提醒。'))void mutate(`/v1/admin/data/documents/${d.id}`,'DELETE',{});}}>管理员删除</button>
      <p style={{overflowWrap:"anywhere"}}>{d.canonical_url}</p><button onClick={()=>inspect(d)}>检查发布条件与证据</button>
      <a href={`/api/backend/v1/admin/data/documents/${d.id}/raw`}>下载原始文件</a></article>)}
    {selected&&inspection&&<article className="card"><h3>当前版本核验</h3>
      <p>{inspection.snapshot.items.map(i=>i.title).join(" / ")}</p>
      <ul>{inspection.blockers.map((b,i)=><li key={i}>{b}</li>)}</ul>
      <h4>资格和事实规则</h4>{inspection.snapshot.rules.map(r=><div key={r.id}>
        <p>{r.field}：{r.expected}</p><blockquote>{inspection.snapshot.evidence.find(e=>e.id===r.evidence_id)?.quote_or_normalized_fact||"证据缺失"}</blockquote>
        <button disabled={busy} onClick={()=>mutate(`/v1/admin/intake/rules/${r.id}`,"PATCH",{action:"approve"})}>逐条确认</button>
        <button disabled={busy} onClick={()=>mutate(`/v1/admin/intake/rules/${r.id}`,"PATCH",{action:"reject"})}>拒绝</button></div>)}
      <details><summary>完整只读 JSON 证据包</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{JSON.stringify(inspection.snapshot,null,2)}</pre></details>
      {inspection.relation_reviews.map(r=><article key={r.id}><p>关系：{r.relation_type} → {r.to_policy_id} · {r.review_status}</p>
        <button disabled={busy} onClick={()=>{const quote=window.prompt("粘贴原始页面中支持该上下级关系的逐字原文，不得仅用文号推断");if(!quote)return;
          const location=window.prompt("原文 DOM/段落位置");if(location)void mutate(`/v1/admin/data/relations/${r.id}`,"PATCH",{action:"approve",quote,location});}}>核对关系原文</button>
        <button disabled={busy} onClick={()=>mutate(`/v1/admin/data/relations/${r.id}`,"PATCH",{action:"reject"})}>拒绝关系候选</button></article>)}
      {(!selected.publication||["rejected","withdrawn"].includes(selected.publication.status))&&<button disabled={busy||!inspection.ready} onClick={()=>publish("submit")}>提交发布审核</button>}
      {selected.publication?.status==="pending"&&<><p>提交人：{selected.publication.submitted_by}；第一审核人：{selected.publication.first_reviewed_by||"待审核"}</p>
        <button disabled={busy} onClick={()=>publish("approve")}>独立审核通过</button><button disabled={busy} onClick={()=>publish("reject")}>驳回发布</button></>}
      {selected.publication&&["pending","published"].includes(selected.publication.status)&&<button disabled={busy} onClick={()=>publish("withdraw")}>撤回</button>}
    </article>}
    {message&&<p role="alert">{message}</p>}
  </section>;
}

const routes:Record<string,string>={CivilServiceWorkbookAdapter:"civil-service-workbook",
  MoEPolicyAdapter:"education-html",YZChsiAdapter:"education-html",UniversityNoticeAdapter:"education-html",
  InstitutionRecruitmentAdapter:"public-recruitment-html",MohrssPublicJobAdapter:"public-recruitment-html",
  RegionalRecruitmentDirectoryAdapter:"public-recruitment-html",OverseasRegistryAdapter:"overseas-html",
  OverseasUniversityProgramAdapter:"overseas-html",GovernmentPolicyAdapter:"entrepreneurship-policy-html"};

export function DataImport() {
  const [message,setMessage]=useState("");const [busy,setBusy]=useState(false);
  async function submit(event:React.FormEvent<HTMLFormElement>) {
    event.preventDefault();if(busy)return;setBusy(true);setMessage("");
    try {
      const data=new FormData(event.currentTarget);const file=data.get("file") as File;
      if(!file.size||file.size>5_000_000)throw Error("请选择不超过5MB的原始 HTML 或 XLSX 文件");
      const config=JSON.parse(String(data.get("config")));
      const route=routes[String(data.get("adapter"))];
      const bytes=new Uint8Array(await file.arrayBuffer());
      let binary="";for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      const body={source_code:data.get("source"),endpoint_name:data.get("endpoint"),source_url:data.get("url"),
        source_item_id:data.get("item"),content_base64:btoa(binary),
        ...(route==="civil-service-workbook"?config:{adapter_config:config})};
      const r=await fetch(`${apiBase}/v1/admin/intake/${route}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      const result=await r.json();if(!r.ok)throw Error(typeof result.detail==="string"?result.detail:JSON.stringify(result.detail));
      setMessage(`导入成功：${JSON.stringify(result)}`);
    } catch(e){setMessage((e as Error).message);}finally{setBusy(false);}
  }
  return <details className="card"><summary>导入官方原始 HTML / XLSX（手动导入，需审核）</summary>
    <form onSubmit={submit} style={{display:"grid",gap:12}}>
      <label>解析器<select name="adapter">{Object.keys(routes).map(r=><option key={r}>{r}</option>)}</select></label>
      <label>Source 编码<input required name="source" placeholder="CM-ENT-005"/></label>
      <label>Endpoint 名称<input required name="endpoint" placeholder="inclusive_finance_policy_fixture"/></label>
      <label>官方原始 URL<input required type="url" name="url"/></label>
      <label>稳定文档标识<input required name="item" placeholder="同一文件各版本使用相同标识"/></label>
      <label>Adapter 配置 JSON<textarea required name="config" defaultValue={'{"path_code":"startup_policy","jurisdiction_path":["CN"]}'}/></label>
      <label>原始文件<input required type="file" name="file" accept=".html,.htm,.xlsx"/></label>
      <button disabled={busy}>{busy?"导入中…":"解析并保存草稿"}</button>
    </form>{message&&<p role="status">{message}</p>}<p>导入成功后刷新页面查看文档。登录、API 密钥及商业受限文件不得导入。</p>
  </details>;
}

"use client";
import {useState} from "react";
import Link from "next/link";
import {useRouter} from "next/navigation";
import {apiBase} from "@/lib/api";
import {Icon} from "@/components/ui";

export function DataFollow({publicationId,itemId,deadline}:{publicationId:string;itemId:string;deadline:string|null}){
  const [message,setMessage]=useState("");const [busy,setBusy]=useState(false),[saved,setSaved]=useState(false),[failed,setFailed]=useState(false);
  const router=useRouter();
  const due=deadline?new Date(deadline).getTime():NaN;
  const canRemind=Number.isFinite(due)&&due-86400000>Date.now();
  async function follow(remind:boolean){
    if(busy)return;setBusy(true);setFailed(false);
    try{
      const r=await fetch(`${apiBase}/v1/data/subscriptions`,{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({publication_id:publicationId,item_id:itemId,...(remind?{remind_before_hours:24}:{})})});
      const data=await r.json();if(!r.ok)throw Error(typeof data.detail==="string"?data.detail:"保存失败，请先登录");
      setMessage(remind?"已加入计划，并设置截止前24小时站内提醒":"已加入我的计划；来源变化时会提示复核");
      setSaved(true);router.refresh();
    }catch(e){setFailed(true);setMessage((e as Error).message);}finally{setBusy(false);}
  }
  return <div className="follow-panel"><div className="actions"><button className="primary" disabled={busy||saved} onClick={()=>follow(false)}><Icon name={saved?'check':'plus'} size={15}/>{busy?'保存中…':saved?'已加入我的计划':'加入我的计划'}</button>
    <button disabled={busy||!canRemind} onClick={()=>follow(true)} aria-describedby={!canRemind?'reminder-hint-'+itemId:undefined}><Icon name="bell" size={15}/>设置截止前24小时提醒</button></div>
    {!canRemind&&<p className="follow-hint" id={'reminder-hint-'+itemId}>{!Number.isFinite(due)?'原文未注明截止日期，可加入计划后自行安排时间。':'截止前24小时的提醒时间已过，可在个人计划中自行安排。'}</p>}
    {message&&<div className={failed?'follow-feedback is-error':'follow-feedback'} role={failed?'alert':'status'}>{message}{!failed&&<Link href="/tracker">查看我的计划<Icon name="arrow" size={14}/></Link>}</div>}</div>;
}

type Subscription={id:string;title:string;publication_id:string;status:string;message:string;read_at:string|null};
export function DataAlerts({initial}:{initial:Subscription[]}){
  const [rows,setRows]=useState(initial);const [message,setMessage]=useState("");
  async function action(id:string,action:"read"|"cancel"){
    try{const r=await fetch(`${apiBase}/v1/data/subscriptions/${id}?action=${action}`,{method:"PATCH"});
      if(!r.ok)throw Error("操作失败");
      setRows(rows=>action==="cancel"?rows.filter(x=>x.id!==id):rows.map(x=>x.id===id?{...x,read_at:new Date().toISOString()}:x));
    }catch(e){setMessage((e as Error).message);}
  }
  return <section className="card"><h2>数据事项与来源变化提醒</h2>
    {!rows.length&&<p>暂无订阅，可从数据中心加入计划。</p>}
    {rows.map(r=><article key={r.id}><h3>{r.title}</h3><p>{r.message||"已订阅，等待提醒"}</p>
      <a href={`/data/${r.publication_id}`}>核对版本与证据</a>{r.message&&!r.read_at&&<button onClick={()=>action(r.id,"read")}>标记已读</button>}
      <button onClick={()=>action(r.id,"cancel")}>取消订阅</button></article>)}{message&&<p role="alert">{message}</p>}
  </section>;
}

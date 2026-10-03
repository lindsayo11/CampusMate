"use client";
import {useState} from "react";
import Link from "next/link";
import {apiBase} from "@/lib/api";
type Notice={id:number;opportunity_id:string;created_at:string;read_at:string|null};
export function NotificationList({initial}:{initial:Notice[]}){
 const [items,setItems]=useState(initial),[error,setError]=useState(""),[more,setMore]=useState(initial.length===100),[busy,setBusy]=useState(false);
 async function loadMore(){if(!items.length)return;setBusy(true);setError("");try{const r=await fetch(`${apiBase}/v1/notifications?before=${items[items.length-1].id}&limit=100`);if(!r.ok)throw Error("加载失败");const data:Notice[]=await r.json();setItems(xs=>[...xs,...data.filter(x=>!xs.some(y=>y.id===x.id))]);setMore(data.length===100)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function mark(id:number){setError("");try{const r=await fetch(`${apiBase}/v1/notifications/${id}/read`,{method:"POST"});if(!r.ok)throw new Error("标记失败，请重试");const updated:Notice=await r.json();setItems(xs=>xs.map(x=>x.id===id?updated:x))}catch(e){setError(e instanceof Error?e.message:"网络异常")}}
 return <><p aria-live="polite">{items.filter(x=>!x.read_at).length} 条未读通知</p>{error&&<p role="alert">{error}</p>}{!items.length?<p>暂无通知</p>:items.map(n=><article className="card" key={n.id}><h2>报名截止提醒 · {n.read_at?"已读":"未读"}</h2><Link href={`/opportunity/${n.opportunity_id}`}>查看相关机会</Link><p>{new Date(n.created_at).toLocaleString("zh-CN")}</p>{!n.read_at&&<button onClick={()=>mark(n.id)}>标为已读</button>}</article>)}{more&&<button disabled={busy} onClick={loadMore}>{busy?"加载中…":"加载更早通知"}</button>}</>;
}

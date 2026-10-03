"use client";
import {useState} from "react";
import Link from "next/link";
import {apiBase} from "@/lib/api";
type Reminder={id:number;opportunity_id:string;due_at:string;sent:boolean};
export function ReminderList({initial}:{initial:Reminder[]}){
 const [items,setItems]=useState(initial),[message,setMessage]=useState(""),[busy,setBusy]=useState<number|null>(null);
 async function cancel(id:number){setBusy(id);try{const r=await fetch(`${apiBase}/v1/reminders/${id}`,{method:"DELETE"});const d=await r.json();if(!r.ok)throw Error(d.detail||"取消失败");setItems(xs=>xs.filter(x=>x.id!==id));setMessage("提醒已取消")}catch(e){setMessage((e as Error).message)}finally{setBusy(null)}}
 return <section><h2>已设置的提醒</h2>{!items.length&&<p>暂无提醒，请从机会详情设置。</p>}{items.map(r=><article className="card" key={r.id}><Link href={`/opportunity/${r.opportunity_id}`}>查看提醒对应机会</Link><p>{new Date(r.due_at).toLocaleString("zh-CN")} · {r.sent?"已投递":"等待投递"}</p>{!r.sent&&<button disabled={busy!==null} onClick={()=>cancel(r.id)}>取消提醒</button>}</article>)}<p role="status">{message}</p></section>
}

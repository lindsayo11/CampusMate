"use client";
import {useState} from "react";
import Link from "next/link";
import {apiBase} from "@/lib/api";

type Reminder={id:number;opportunity_id:string;due_at:string;sent:boolean};
export function ReminderList({initial}:{initial:Reminder[]}){
  const [items,setItems]=useState(initial),[message,setMessage]=useState(""),[busy,setBusy]=useState<number|null>(null);
  async function cancel(id:number){setBusy(id);try{const r=await fetch(`${apiBase}/v1/reminders/${id}`,{method:"DELETE"});const d=await r.json();if(!r.ok)throw Error(d.detail||"取消失败");setItems(xs=>xs.filter(x=>x.id!==id));setMessage("提醒已取消")}catch(e){setMessage((e as Error).message)}finally{setBusy(null)}}
  return <div className="notification-feed">{!items.length&&<p className="notification-empty">暂无机会提醒</p>}{items.map(r=><article className="notification-item" key={r.id}><h3>校园机会提醒</h3><p>{new Date(r.due_at).toLocaleString("zh-CN")} · {r.sent?"已投递":"等待投递"}</p><div className="notification-item-actions"><Link href={`/opportunity/${r.opportunity_id}`}>查看机会</Link>{!r.sent&&<button disabled={busy!==null} onClick={()=>cancel(r.id)}>取消</button>}</div></article>)}{message&&<p role="status">{message}</p>}</div>;
}

"use client";
import {useEffect,useState} from 'react';
import {apiBase} from '@/lib/api';
type Row={id:string;title:string;due_at:string;status:string;read_at:string|null};
export function PlanReminderPanel(){
 const [rows,setRows]=useState<Row[]>([]),[error,setError]=useState('');
 async function load(){const r=await fetch(apiBase+'/v1/development-agent/reminders');if(!r.ok)throw Error('计划提醒加载失败');setRows(await r.json());}
 useEffect(()=>{void load().catch(e=>setError(e.message));},[]);
 async function act(id:string,operation:string){try{const r=await fetch(`${apiBase}/v1/development-agent/reminders/${id}?operation=${operation}`,{method:'PATCH'});if(!r.ok)throw Error('操作失败');await load();}catch(e){setError((e as Error).message);}}
 return <div className="notification-feed">{error&&<p role="alert">{error}</p>}{!rows.length&&<p className="notification-empty">暂无提醒</p>}{rows.map(r=><article className="notification-item" key={r.id}><h3>{r.title}</h3><p>{new Date(r.due_at).toLocaleString()} · {r.status==='pending'?'等待提醒':'已提醒'}{r.read_at?' · 已读':''}</p><div className="notification-item-actions"><button onClick={()=>act(r.id,'read')}>标为已读</button><button onClick={()=>act(r.id,'cancel')}>取消</button></div></article>)}</div>;
}

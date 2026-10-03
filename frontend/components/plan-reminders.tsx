"use client";
import {useEffect,useState} from 'react';
import {apiBase} from '@/lib/api';
type Row={id:string;title:string;due_at:string;status:string;read_at:string|null};
export function PlanReminderPanel(){
 const [rows,setRows]=useState<Row[]>([]),[error,setError]=useState('');
 async function load(){const r=await fetch(apiBase+'/v1/development-agent/reminders');if(!r.ok)throw Error('计划提醒加载失败');setRows(await r.json());}
 useEffect(()=>{void load().catch(e=>setError(e.message));},[]);
 async function act(id:string,operation:string){try{const r=await fetch(`${apiBase}/v1/development-agent/reminders/${id}?operation=${operation}`,{method:'PATCH'});if(!r.ok)throw Error('操作失败');await load();}catch(e){setError((e as Error).message);}}
 return <section><h2>个人计划提醒</h2>{error&&<p role="alert">{error}</p>}{!rows.length&&<p>暂无计划提醒，可在发展助手中选择计划并设置时间。</p>}{rows.map(r=><article className="card" key={r.id}><h3>{r.title}</h3><p>{new Date(r.due_at).toLocaleString()} · {r.status==='pending'?'等待提醒':'已提醒'} {r.read_at?'· 已读':''}</p><button onClick={()=>act(r.id,'read')}>标记已读</button><button onClick={()=>act(r.id,'cancel')}>取消提醒</button></article>)}</section>;
}

"use client";
import {useState} from 'react';
import Link from 'next/link';
import {apiBase} from '@/lib/api';
type Alert={id:number;task_id:number;title:string;team_id:string;team_title:string;due_at:string;created_at:string;read_at:string|null;overdue:boolean};
type Result={items:Alert[];has_more:boolean};
export function TaskAlertList({initial}:{initial:Result}){
 const [items,setItems]=useState(initial.items),[more,setMore]=useState(initial.has_more),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 async function load(older=false){if(busy)return;setBusy(true);setMessage('');try{const before=older&&items.length?`?before=${items[items.length-1].id}`:'';const r=await fetch(apiBase+'/v1/task-alerts'+before,{cache:'no-store'});if(!r.ok)throw Error('读取任务通知失败');const data:Result=await r.json();setItems(previous=>older?[...previous,...data.items]:data.items);setMore(data.has_more)}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}
 async function read(id:number){if(busy)return;setBusy(true);try{const r=await fetch(`${apiBase}/v1/task-alerts/${id}/read`,{method:'POST'});if(!r.ok)throw Error('任务状态可能已变化，请刷新');setItems(rows=>rows.map(a=>a.id===id?{...a,read_at:new Date().toISOString()}:a))}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}
 return <section><h2>队伍任务提醒</h2><p>截止前 24 小时内或逾期未完成的任务会提醒当前负责人。改期、转交、完成或退出后，刷新即可同步。</p><button disabled={busy} onClick={()=>void load()}>刷新任务通知</button>{!items.length&&<p>暂无待处理任务通知</p>}{items.map(a=><article className="card" key={a.id}><h3>{a.title} · {a.overdue?'已逾期':'即将截止'}</h3><p>{a.team_title} · 截止 {new Date(a.due_at).toLocaleString('zh-CN')}</p><Link href={`/team-manager#team-${a.team_id}`}>前往队伍处理任务</Link><p>{a.read_at?'已读':'未读'}</p>{!a.read_at&&<button disabled={busy} onClick={()=>void read(a.id)}>标记任务通知已读</button>}</article>)}{more&&<button disabled={busy} onClick={()=>void load(true)}>加载更早任务通知</button>}<p role="status">{message}</p></section>;
}

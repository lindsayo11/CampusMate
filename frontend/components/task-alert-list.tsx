"use client";
import {useState} from 'react';
import Link from 'next/link';
import {apiBase} from '@/lib/api';
import {Icon} from '@/components/ui';

type Alert={id:number;task_id:number;title:string;team_id:string;team_title:string;due_at:string;created_at:string;read_at:string|null;overdue:boolean};
type Result={items:Alert[];has_more:boolean};

export function TaskAlertList({initial}:{initial:Result}){
  const [items,setItems]=useState(initial.items),[more,setMore]=useState(initial.has_more),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  async function load(older=false){if(busy)return;setBusy(true);setMessage('');try{const before=older&&items.length?`?before=${items[items.length-1].id}`:'';const r=await fetch(apiBase+'/v1/task-alerts'+before,{cache:'no-store'});if(!r.ok)throw Error('读取任务通知失败');const data:Result=await r.json();setItems(previous=>older?[...previous,...data.items]:data.items);setMore(data.has_more)}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}
  async function read(id:number){if(busy)return;setBusy(true);try{const r=await fetch(`${apiBase}/v1/task-alerts/${id}/read`,{method:'POST'});if(!r.ok)throw Error('任务状态可能已变化，请刷新');setItems(rows=>rows.map(a=>a.id===id?{...a,read_at:new Date().toISOString()}:a))}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}
  return <div className="notification-feed"><button className="notification-refresh-button" disabled={busy} onClick={()=>void load()}><Icon name="refresh" size={14}/>刷新</button>{!items.length&&<p className="notification-empty">暂无任务通知</p>}{items.map(a=><article className="notification-item" key={a.id}><h3>{a.title}</h3><p>{a.team_title} · {a.overdue?'已逾期':'即将截止'} · {new Date(a.due_at).toLocaleString('zh-CN')}</p><div className="notification-item-actions"><Link href={`/team-manager#team-${a.team_id}`}>处理任务</Link>{!a.read_at&&<button disabled={busy} onClick={()=>void read(a.id)}>标为已读</button>}</div></article>)}{more&&<button disabled={busy} onClick={()=>void load(true)}>加载更多</button>}{message&&<p role="status">{message}</p>}</div>;
}

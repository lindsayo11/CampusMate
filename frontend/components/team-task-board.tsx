"use client";
import {useEffect,useState} from "react";
import {apiBase} from "@/lib/api";
type Task={id:number;title:string;description:string;assignee:string|null;status:string;due_at:string|null;version:number};
const labels:Record<string,string>={todo:"待开始",doing:"进行中",done:"已完成",cancelled:"已取消"};
export function TeamTaskBoard({teamId,members,owner,myId}:{teamId:string;members:string[];owner:boolean;myId:string}) {
 const [tasks,setTasks]=useState<Task[]>([]),[status,setStatus]=useState(""),[busy,setBusy]=useState(false),[editing,setEditing]=useState<Task|null>(null);
 async function call(path:string,method="GET",data?:unknown){
  const r=await fetch(`${apiBase}/v1/teams/${teamId}/tasks${path}`,{method,cache:"no-store",headers:{"Content-Type":"application/json"},...(data===undefined?{}:{body:JSON.stringify(data)})});
  if(!r.ok){const e=await r.json();throw new Error(typeof e.detail==="string"?e.detail:"输入无效，请检查字段和日期")}
  return r.json();
 }
 async function refresh(){setTasks(await call(""))}
 useEffect(()=>{let alive=true;call("").then(rows=>{if(alive)setTasks(rows)}).catch(()=>{if(alive)setStatus("无法读取任务")});return ()=>{alive=false}},[teamId]);
 async function run(fn:()=>Promise<void>){if(busy)return;setBusy(true);setStatus("");try{await fn();await refresh()}catch(e){setStatus(String(e));await refresh().catch(()=>{})}finally{setBusy(false)}}
 const active=tasks.filter(t=>t.status!=="cancelled"),done=active.filter(t=>t.status==="done").length;
 return <section aria-label="队伍任务"><h4>任务分工 · {done}/{active.length} 已完成</h4><p>队长创建和分配任务，负责人更新自己的进度。截止时间按当前设备时区填写。</p><button disabled={busy} onClick={()=>void run(refresh)}>刷新任务</button>
 {owner&&<form key={editing?.id??"new"} onSubmit={e=>{e.preventDefault();const form=e.currentTarget;const f=new FormData(form);void run(async()=>{const due=String(f.get("due_at")||"");const payload={title:f.get("title"),description:f.get("description"),assignee:f.get("assignee")||null,due_at:due?new Date(due).toISOString():null,...(editing?{version:editing.version}:{})};await call(editing?`/${editing.id}`:"",editing?"PUT":"POST",payload);setEditing(null);form.reset();setStatus(editing?"任务已更新":"任务已创建")})}}>
 <label>任务标题<input name="title" required maxLength={120} defaultValue={editing?.title??""}/></label>
 <label>任务说明<textarea name="description" maxLength={4000} defaultValue={editing?.description??""}/></label>
 <label>任务负责人<select name="assignee" defaultValue={editing?.assignee??""}><option value="">待分配</option>{members.map(m=><option value={m} key={m}>{m}</option>)}</select></label>
 <label>任务截止时间<input name="due_at" type="datetime-local" defaultValue={editing?.due_at?localTime(editing.due_at):""}/></label>
 <button disabled={busy}>{editing?"保存任务":"创建任务"}</button>{editing&&<button type="button" onClick={()=>setEditing(null)}>取消编辑</button>}</form>}
 {!tasks.length&&<p>暂无任务。队长可以添加下一步要做的事。</p>}
 {tasks.map(t=><div className="form-card" key={t.id}><h5>{t.title}</h5><p>{t.description}</p><p>负责人：{t.assignee||"待分配"} · {labels[t.status]}</p>{t.due_at&&<p>截止：{new Date(t.due_at).toLocaleString()}{!["done","cancelled"].includes(t.status)&&new Date(t.due_at).getTime()<Date.now()?" · 已逾期":""}</p>}
 <div className="chips">{Object.entries(labels).filter(([key])=>key!==t.status&&(owner||(t.assignee===myId&&t.status!=="cancelled"&&key!=="cancelled"))).map(([key,label])=><button disabled={busy} key={key} onClick={()=>void run(async()=>{await call(`/${t.id}/status`,"POST",{status:key,version:t.version})})}>{label}</button>)}{owner&&<button disabled={busy} onClick={()=>setEditing(t)}>编辑任务</button>}</div></div>)}<p role="status">{status}</p></section>;
}
function localTime(iso:string){const date=new Date(iso);return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16)}

"use client";
import {useEffect,useState} from "react";
import {apiBase} from "@/lib/api";
type Event={id:number;actor:string;action:string;resource:string;created_at:string};
export default function Audit(){
 const [items,setItems]=useState<Event[]>([]),[message,setMessage]=useState(""),[busy,setBusy]=useState(false);
 async function load(){const r=await fetch(apiBase+'/v1/admin/audit',{cache:'no-store'});if(!r.ok)throw Error('读取审计失败，请核对权限');setItems(await r.json())}
 useEffect(()=>{load().catch(e=>setMessage(e.message))},[]);
 return <div className="shell"><h1>审计记录与内容下线</h1><form className="form-card" onSubmit={async e=>{e.preventDefault();if(busy)return;const id=String(new FormData(e.currentTarget).get('id')).trim();if(!confirm(`确认下线机会 ${id}？`))return;setBusy(true);try{const r=await fetch(`${apiBase}/v1/admin/opportunities/${encodeURIComponent(id)}/unpublish`,{method:'POST'});const d=await r.json();if(!r.ok)throw Error(d.detail||'下线失败');await load();setMessage('机会已下线，审计已记录')}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}}><label>需要下线的机会 ID<input name="id" required maxLength={40}/></label><button disabled={busy}>下线机会</button></form><p role="status">{message}</p><h2>最近 100 条操作</h2><button onClick={()=>load().catch(e=>setMessage(e.message))}>刷新审计</button>{!items.length&&<p>暂无审计记录。</p>}<table><thead><tr><th>时间</th><th>操作人</th><th>操作</th><th>对象</th></tr></thead><tbody>{items.map(x=><tr key={x.id}><td>{new Date(x.created_at).toLocaleString('zh-CN')}</td><td>{x.actor}</td><td>{x.action}</td><td>{x.resource}</td></tr>)}</tbody></table></div>
}

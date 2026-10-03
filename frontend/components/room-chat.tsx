"use client";
import {useEffect, useRef, useState} from "react";
import {apiBase} from "@/lib/api";
import {Icon,EmptyState} from "@/components/ui";
type Message = {id:number; sender:string; body:string; hidden:boolean;created_at?:string};
type Page = {items:Message[]; has_more:boolean; oldest_id:number|null; newest_id:number|null};
async function request(path:string, data?:unknown, signal?:AbortSignal) {
 const response = await fetch(apiBase+path, {cache:"no-store", signal,
  ...(data===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)})});
 if (!response.ok) throw new Error(response.status===404?"会话已不可用，请重新选择会话":"连接失败，稍后自动重试");
 return response.json();
}
export function RoomChat({roomId,myId}:{roomId:string;myId?:string}) {
 const [messages,setMessages]=useState<Message[]>([]), [hasOlder,setHasOlder]=useState(false);
 const [body,setBody]=useState(""), [status,setStatus]=useState("正在连接"), [sending,setSending]=useState(false), [loadingOlder,setLoadingOlder]=useState(false);
 const cursor=useRef(0), oldest=useRef<number|null>(null), initialized=useRef(false);
 const synchronize=useRef<()=>Promise<void>>(async()=>{});
 function merge(items:Message[]) {
  setMessages(previous=>Array.from(new Map([...previous,...items].map(m=>[m.id,m])).values()).sort((a,b)=>a.id-b.id));
  for (const m of items) {cursor.current=Math.max(cursor.current,m.id);oldest.current=Math.min(oldest.current??m.id,m.id);}
 }
 useEffect(()=>{
  const controller=new AbortController(); let busy=false, stopped=false;
  async function sync() {
   if(busy||stopped||document.visibilityState==="hidden") return;
   busy=true;
   try {
    if(!initialized.current) {
     const p:Page=await request(`/v1/rooms/${roomId}/history`,undefined,controller.signal);
     if(stopped)return;
     merge(p.items);setHasOlder(p.has_more);initialized.current=true;
    } else {
     // Drain every page after the last persisted ID. A disconnect can span >100 messages.
     let more=true;
     while(more&&!stopped) {
      const p:Page=await request(`/v1/rooms/${roomId}/history?after=${cursor.current}`,undefined,controller.signal);
      if(stopped)return;
      merge(p.items);more=p.has_more;
     }
     // Refresh the latest window to pick up moderation removals as well as new messages.
     const p:Page=await request(`/v1/rooms/${roomId}/history`,undefined,controller.signal);
     if(stopped)return;
     merge(p.items);
    }
    if(cursor.current&&document.visibilityState==="visible"&&document.hasFocus())
     await request(`/v1/rooms/${roomId}/read`,{message_id:cursor.current},controller.signal);
    if(!stopped)setStatus("已连接 · 每 3 秒自动同步");
   } catch(error) {if(!stopped)setStatus(String(error));}
   finally {busy=false;}
  }
  synchronize.current=sync;void sync();
  const timer=setInterval(()=>void sync(),3000);
  const resume=()=>void sync();
  window.addEventListener("online",resume);window.addEventListener("focus",resume);document.addEventListener("visibilitychange",resume);
  return ()=>{stopped=true;controller.abort();clearInterval(timer);window.removeEventListener("online",resume);window.removeEventListener("focus",resume);document.removeEventListener("visibilitychange",resume);};
 },[roomId]);
 async function older() {
  if(!oldest.current||loadingOlder)return;
  setLoadingOlder(true);
  try {const p:Page=await request(`/v1/rooms/${roomId}/history?before=${oldest.current}`);merge(p.items);setHasOlder(p.has_more);}
  catch(error){setStatus(String(error));}finally{setLoadingOlder(false);}
 }
 async function send(event:React.FormEvent) {
  event.preventDefault();if(sending||!body.trim())return;setSending(true);
  try {await request(`/v1/rooms/${roomId}/messages`,{body});setBody("");await synchronize.current();}
  catch{setStatus("发送未确认，请检查消息记录后再重试，避免重复发送");}finally{setSending(false);}
 }
 return <div className="room-chat"><div className="chat-toolbar"><span role="status">{status}</span><button onClick={()=>void synchronize.current()}>刷新消息</button></div>
  {hasOlder&&<button disabled={loadingOlder} onClick={()=>void older()}>{loadingOlder?"加载中…":"加载更早消息"}</button>}
  <div className="message-history" aria-label="聊天记录">{!messages.length&&<EmptyState icon="users" title="还没有消息" description="打个招呼，说说你正在准备的事情。"/>}{messages.map(m=><article className="chat-message" key={m.id}><span className="user-avatar">{m.sender===myId?'我':m.sender.slice(0,1).toUpperCase()}</span><div><b title={m.sender}>{m.sender===myId?'我':m.sender}</b>{m.created_at&&<time>{new Date(m.created_at).toLocaleString('zh-CN',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})}</time>}<p>{m.body}</p></div>{!m.hidden&&<button onClick={async()=>{try{await request(`/v1/messages/${m.id}/report`,{reason:"用户请求人工复核"});setStatus("举报已提交，等待人工处理");}catch(error){setStatus(String(error));}}}>举报</button>}</article>)}</div>
  <form className="chat-composer" onSubmit={send}><div className="chat-compose-box"><label htmlFor={'message-'+roomId}>当前房间 · 消息</label><textarea id={'message-'+roomId} aria-label="消息" placeholder="发送一条消息，开始讨论…" maxLength={2000} required value={body} onChange={e=>setBody(e.target.value)}/><div className="composer-tools"><span>仅房间成员可查看 · 最多 2,000 字</span><button className="primary" disabled={sending||!body.trim()}>{sending?"发送中…":"发送"}<Icon name="send" size={13}/></button></div></div></form></div>;
}

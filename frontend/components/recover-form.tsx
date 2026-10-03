"use client";
import {useState} from "react";
export default function Recover(){
 const [email,setEmail]=useState(""),[sent,setSent]=useState(false),[busy,setBusy]=useState(false),[done,setDone]=useState(false),[message,setMessage]=useState("");
 async function submit(method:"POST"|"PATCH",data:unknown){
  if(busy)return;setBusy(true);setMessage("处理中…");
  try{const r=await fetch("/api/session/recovery",{method,headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});const value=await r.json();setMessage(value.message||value.detail);if(r.ok){if(method==="POST")setSent(true);else setDone(true)}}
  catch{setMessage("网络错误。如果刚才正在修改密码，请先尝试新密码登录，避免重复提交。")}finally{setBusy(false)}
 }
 return <div className="shell narrow"><h1>找回密码</h1><p>通过注册邮箱中的一次性验证码重设密码。验证码只用于本次找回，请勿提供给他人。</p>
 {!done&&<><form className="form-card" onSubmit={e=>{e.preventDefault();void submit("POST",{email})}}><label>注册邮箱<input type="email" required maxLength={254} autoComplete="email" value={email} onChange={e=>{setEmail(e.target.value);setSent(false)}}/></label><button disabled={busy}>{sent?"重新发送验证码":"发送验证码"}</button></form>
 {sent&&<form className="form-card" onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);if(f.get("password")!==f.get("confirmation")){setMessage("两次输入的密码不一致");return}void submit("PATCH",{email,token:f.get("token"),password:f.get("password")})}}>
 <label>邮件验证码<input name="token" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6,10}" minLength={6} maxLength={10} required/></label>
 <label>新密码<input name="password" type="password" autoComplete="new-password" minLength={8} maxLength={1024} required/></label>
 <label>再次输入新密码<input name="confirmation" type="password" autoComplete="new-password" minLength={8} maxLength={1024} required/></label>
 <button disabled={busy}>确认重设密码</button></form>}</>}
 <p role="status" aria-live="polite">{message}</p><a href="/login">返回登录</a></div>;
}

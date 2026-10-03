"use client";
import { useState } from "react";
import Link from "next/link";
import { apiBase } from "@/lib/api";

export function ActionPanel({opportunityId,deadline}:{opportunityId:string;deadline:string}){
  const expired=new Date(deadline).getTime()<=Date.now();
  const [message,setMessage]=useState(""); const [busy,setBusy]=useState(false);
  async function call(path:string,body:object,success:string){setBusy(true);setMessage("");try{const r=await fetch(`${apiBase}${path}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});if(!r.ok){const d=await r.json();throw new Error(typeof d.detail==="string"?d.detail:"操作失败")}setMessage(success)}catch(e){setMessage(e instanceof Error?e.message:"网络异常，请重试") }finally{setBusy(false)}}
  return <aside><p>{expired?"报名已截止":"报名截止"}</p><strong>{new Date(deadline).toLocaleDateString("zh-CN")}</strong><button disabled={busy||expired} onClick={()=>call("/v1/tools/tracker_write",{opportunity_id:opportunityId,stage:"saved"},"已加入行动看板")}>加入行动看板</button><button className="secondary" disabled={busy||expired} onClick={()=>call("/v1/tools/deadline_remind",{opportunity_id:opportunityId,hours_before:24},"已设置截止前 24 小时提醒")}>设置提醒</button><Link className="panel-link" href={`/eligibility?opportunity_id=${encodeURIComponent(opportunityId)}`}>判断参与资格 →</Link><Link className="panel-link" href="/tracker">查看我的行动 →</Link><Link className="panel-link" href="/teams">寻找队友或联系同学 →</Link>{message&&<small role="status" className="feedback">{message}</small>}</aside>
}

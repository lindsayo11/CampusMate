"use client";

import {useState} from "react";
import {useRouter} from "next/navigation";
import {apiBase} from "@/lib/api";
import {Icon} from "@/components/ui";

export function ManualRefreshButton(){
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const router=useRouter();
  async function refresh(){
    if(busy)return;
    setBusy(true);setMessage("");
    try{
      const response=await fetch(`${apiBase}/v1/data/refresh`,{method:"POST"});
      const result=await response.json();
      if(!response.ok)throw new Error(typeof result.detail==="string"?result.detail:"暂时无法更新");
      setMessage(result.sources?`已加入 ${result.sources} 个来源的更新队列`:"暂无可更新的官方来源");
      router.refresh();
    }catch(error){setMessage(error instanceof Error?error.message:"暂时无法更新");}
    finally{setBusy(false);}
  }
  return <span className="manual-refresh-control"><button className="button secondary" type="button" onClick={()=>void refresh()} disabled={busy}><Icon name="refresh" size={15}/>{busy?"提交中…":"立即更新"}</button>{message&&<small role="status">{message}</small>}</span>;
}

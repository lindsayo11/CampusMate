"use client";
import { useState } from "react";

export function OverseasReviewControls({type,id}:{type:"institution"|"program"|"cycle"|"assertion";id:string}){
  const [message,setMessage]=useState("");
  async function review(action:"approve"|"reject"|"expire"){
    setMessage("提交中…");
    const response=await fetch(`/api/backend/v1/admin/intake/overseas/${type}/${id}/review`,{
      method:"PATCH",headers:{"content-type":"application/json"},body:JSON.stringify({action,note:"管理后台审核"})
    });
    setMessage(response.ok?"已更新，请刷新查看":"更新失败");
  }
  return <div className="chips"><button onClick={()=>review("approve")}>确认</button><button onClick={()=>review("reject")}>拒绝</button><button onClick={()=>review("expire")}>标记过期</button>{message&&<span>{message}</span>}</div>;
}

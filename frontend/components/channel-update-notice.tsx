"use client";

import Link from "next/link";
import {useEffect,useState} from "react";
import {apiBase} from "@/lib/api";
import {Icon} from "@/components/ui";
import {channelHref} from "@/lib/development-channels";

type ChannelNotice={path:string;name:string;updated_at:string;source_count:number};
type UpdateResponse={available:boolean;notice:ChannelNotice|null};

function seenKey(path:string){return `campusmate.channel-summary.seen.${path}`}

export function ChannelUpdateNotice({authenticated,channel}:{authenticated:boolean;channel?:string}){
 const [notice,setNotice]=useState<ChannelNotice|null>(null);
 useEffect(()=>{
   if(!authenticated)return;
   let alive=true;
   async function load(){
    try{
     const response=await fetch(`${apiBase}/v1/data/channel-updates`,{cache:"no-store"});
     if(!response.ok)return;
     const data=await response.json() as UpdateResponse;
     const current=data.notice;
     if(!alive||!data.available||!current)return;
     if(channel&&current.path!==channel){setNotice(null);return;}
     if(window.localStorage.getItem(seenKey(current.path))!==current.updated_at)setNotice(current);
    }catch{/* A notice must never block the workspace. */}
   }
   void load();
   const timer=window.setInterval(()=>void load(),10*60*1000);
   return()=>{alive=false;window.clearInterval(timer)};
 },[authenticated,channel]);
 function dismiss(markSeen:boolean){
  if(notice&&markSeen)window.localStorage.setItem(seenKey(notice.path),notice.updated_at);
  setNotice(null);
 }
 if(!notice||!authenticated||(channel&&notice.path!==channel))return null;
 return <aside className="channel-update-notice" role="status" aria-label={`${notice.name}更新`}>
  <span className="channel-update-notice-icon"><Icon name="bell" size={16}/></span>
  <span className="channel-update-notice-copy"><strong>{notice.name}有新总结</strong><small>已根据 {notice.source_count} 份原文更新</small></span>
  <Link href={channelHref(notice.path)} onClick={()=>dismiss(true)}>查看</Link>
  <button type="button" aria-label="关闭更新提示" onClick={()=>dismiss(true)}><Icon name="close" size={14}/></button>
 </aside>;
}

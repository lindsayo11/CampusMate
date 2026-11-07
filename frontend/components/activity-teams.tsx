"use client";
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {apiBase} from '@/lib/api';
import type {CatalogItem} from '@/lib/catalog';
import {teamLabels,availabilityLabels} from '@/lib/explore';
import {Icon} from './ui';
import {NoticeArtwork} from './notice-artwork';
import {NoticeDialog} from './notice-detail';
import styles from './explore.module.css';

type Team={id:string;title:string;description:string;capacity:number;member_count:number;state:string;is_member:boolean;is_owner:boolean;recruiting:boolean;request_status:string|null;room_id?:string};
type ActivityResult={activity:CatalogItem;teams:Team[]};
export async function activityApi(path:string,body?:unknown){
 const r=await fetch(apiBase+'/v1/activity-teams'+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const data=await r.json().catch(()=>null);
 if(!r.ok)throw Error(r.status===401?'请先登录，再参与组队。':typeof data?.detail==='string'?data.detail:'操作未完成，请重试。');
 return data;
}
export function ActivityTeams({publicationId,itemId}:{publicationId:string;itemId:string}){
 const [data,setData]=useState<ActivityResult|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[formOpen,setFormOpen]=useState(false),[detail,setDetail]=useState(false),[messages,setMessages]=useState<Record<string,string>>({});
 const endpoint='/activity/'+encodeURIComponent(publicationId)+'/'+encodeURIComponent(itemId);
 async function refresh(){setData(await activityApi(endpoint))}
 useEffect(()=>{let alive=true;activityApi(endpoint).then(d=>{if(alive)setData(d)}).catch(e=>{if(alive)setError(e.message)}).finally(()=>{if(alive)setLoading(false)});return()=>{alive=false}},[endpoint]);
 async function run(action:()=>Promise<void>){if(busy)return;setBusy(true);setError('');setNotice('');try{await action();await refresh()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <div className={styles.surface}>
  <header className={styles.heading}><div><h1>活动组队</h1><Link href="/teams">← 返回组队目录</Link></div><Link className={styles.secondary} href="/team-manager">我的团队<Icon name="arrow" size={15}/></Link></header>
  {error&&<div className={styles.error} role="alert">{error} <button onClick={()=>void run(refresh)} disabled={busy}>重试</button><Link href="/login">登录</Link></div>}
  {loading&&<div className={styles.loading} role="status">正在读取活动与队伍…</div>}
  {notice&&<p role="status">{notice}</p>}
  {data&&<><div className={styles.activityIntro}><NoticeArtwork paths={data.activity.paths} title={data.activity.title} seedKey={data.activity.id}/><div><span className={styles.category}>{data.activity.paths?.map(p=>p.name).join(' · ')||'公开活动'}</span><h2>{data.activity.title}</h2><p>{data.activity.source.name} · {availabilityLabels[data.activity.availability||'']||'请核对原文'}</p><button type="button" onClick={()=>setDetail(true)}>查看公告与原文<Icon name="arrow" size={14}/></button></div></div>
   <div className={styles.sectionHead}><h2>正在这里集结 · {data.teams.length} 支队伍</h2><button className={styles.primary} disabled={busy} onClick={()=>setFormOpen(v=>!v)}><Icon name="plus" size={16}/>{formOpen?'收起创建表单':'创建队伍'}</button></div>
   <p className={styles.muted}>组队不等于官方报名；提交加入申请后，由队长确认。</p>
   {formOpen&&<form className={styles.teamForm} onSubmit={e=>{e.preventDefault();const form=new FormData(e.currentTarget);void run(async()=>{await activityApi('',{publication_id:publicationId,item_id:itemId,title:form.get('title'),capacity:Number(form.get('capacity')),description:form.get('description')});setFormOpen(false);setNotice('队伍已创建，可以邀请同学或等待加入申请。')})}}>
    <h3>围绕这条公告创建队伍</h3><div className={styles.formGrid}><label>队伍名称<input name="title" required maxLength={100} placeholder="给你的队伍起个名字"/></label><label>人数上限（含队长）<input name="capacity" type="number" min={2} max={20} defaultValue={5} required/></label></div>
    <label>招募说明<textarea name="description" maxLength={600} placeholder="想做什么、需要哪些技能、预计每周投入多少时间…" rows={3}/></label>
    <div className={styles.actions}><button className={styles.primary} disabled={busy}>{busy?'正在创建…':'确认创建'}</button><button type="button" disabled={busy} onClick={()=>setFormOpen(false)}>取消</button></div>
   </form>}
   <div className={styles.teamGrid}>{data.teams.map(team=><article className={styles.teamCard} key={team.id}>
    <div className={styles.sectionHead}><h3>{team.title}</h3><span className={styles.status} data-state={team.state}>{teamLabels[team.state]}</span></div>
    <p>{team.description||'队长暂未填写招募说明。'}</p><small>{team.member_count} / {team.capacity} 位成员{team.is_owner?' · 你是队长':''}</small>
    {team.is_member?<div className={styles.actions} style={{marginTop:18}}><Link className={styles.primary} href={'/teams?room='+encodeURIComponent(team.room_id!)}>进入队伍会话</Link>{team.is_owner&&<button disabled={busy} onClick={()=>void run(async()=>{await activityApi('/'+team.id+'/recruitment',{recruiting:!team.recruiting});setNotice(team.recruiting?'已暂停招募':'已重新开放招募')})}>{team.recruiting?'暂停招募':'开放招募'}</button>}</div>:
      team.request_status==='pending'?<p role="status">申请已提交，等待队长确认。<Link href="/team-manager">查看我的团队</Link></p>:
      team.state==='recruiting'?<form onSubmit={e=>{e.preventDefault();void run(async()=>{await activityApi('/'+team.id+'/request',{message:messages[team.id]||''});setNotice('申请已提交，等待队长确认。')})}}>
       <textarea aria-label={'向'+team.title+'介绍自己'} value={messages[team.id]||''} maxLength={300} placeholder="简单介绍你的技能与可投入时间（选填）" onChange={e=>setMessages(m=>({...m,[team.id]:e.target.value}))}/>
       <button className={styles.primary} disabled={busy}>申请加入<Icon name="arrow" size={14}/></button>{team.request_status==='rejected'&&<p className={styles.muted}>上次申请未通过，可以补充说明后重新申请。</p>}
      </form>:<p className={styles.muted}>{team.state==='full'?'当前队伍人数已满。':'队长暂时关闭了招募。'}</p>}
   </article>)}</div>
   {!data.teams.length&&!formOpen&&<div className={styles.empty}><h3>还没有队伍，成为第一个发起人吧</h3><button onClick={()=>setFormOpen(true)}>创建队伍</button></div>}
  </>}
  {detail&&<NoticeDialog publicationId={publicationId} itemId={itemId} onClose={()=>setDetail(false)}/>}
 </div>;
}

export function TeamJoinRequests({onChange}:{onChange:()=>Promise<void>}){
 const [requests,setRequests]=useState<{id:string;team_title:string;display_name:string;message:string}[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[loaded,setLoaded]=useState(false);
 async function refresh(){setRequests(await activityApi('/requests'));setLoaded(true)}
 useEffect(()=>{void refresh().catch(e=>setError(e.message))},[]);
 async function decide(id:string,action:string){if(busy)return;setBusy(true);setError('');try{await activityApi('/requests/'+id+'/decision',{action});await refresh();await onChange()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <section className={styles.surface+' '+styles.joinRequests} aria-label="入队申请"><h2>入队申请{loaded?' · '+requests.length:''}</h2>{error&&<p role="alert" className={styles.error}>{error}<button onClick={()=>void refresh().catch(e=>setError(e.message))}>重试</button></p>}{loaded&&!requests.length&&<p className={styles.muted}>暂无待处理的入队申请。</p>}
  {requests.map(r=><article className={styles.requestRow} key={r.id}><div><strong>{r.display_name} → {r.team_title}</strong><p>{r.message||'对方未填写附言'}</p></div><div className={styles.actions}><button className={styles.primary} disabled={busy} onClick={()=>void decide(r.id,'accept')}>接受申请</button><button disabled={busy} onClick={()=>void decide(r.id,'reject')}>拒绝</button></div></article>)}
 </section>;
}

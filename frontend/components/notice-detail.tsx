"use client";
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {apiBase} from '@/lib/api';
import {channelHref,getChannel,noticeHref,type ChannelCode} from '@/lib/development-channels';
import {availabilityLabels,noticeDate,safeSourceUrl,type Publication,type SourceText} from '@/lib/explore';
import {Icon} from './ui';
import {NoticeArtwork} from './notice-artwork';
import {DataFollow} from './data-follow';
import {DataCorrection} from './data-correction';
import styles from './explore.module.css';

async function read<T>(url:string,signal?:AbortSignal):Promise<T>{
  const response=await fetch(apiBase+url,{signal,cache:'no-store'});
  if(!response.ok)throw Error(response.status===404?'这条公告已撤回或暂不可见。':response.status===401?'请登录后继续。':'暂时无法读取，请重试。');
  return response.json();
}

export function NoticeDetail({data,itemId,channel}:{data:Publication;itemId?:string;channel?:ChannelCode}){
  // A publication may use a descendant path (e.g. overseas_masters). Its API
  // already controls visibility; the channel here is the user's return context.
  const visibleItems=data.items;
  const [selected,setSelected]=useState(itemId||visibleItems[0]?.id),[sourceOpen,setSourceOpen]=useState(false);
  const [source,setSource]=useState<SourceText|null>(null),[sourceError,setSourceError]=useState(''),[retry,setRetry]=useState(0);
  const sourceRef=useRef<HTMLElement>(null);
  const item=visibleItems.find(x=>x.id===selected);
  useEffect(()=>{setSource(null);setSourceError('');if(!sourceOpen)return;const controller=new AbortController();
    read<SourceText>('/v1/data/publications/'+encodeURIComponent(data.id)+'/source',controller.signal).then(setSource).catch(e=>{if(e.name!=='AbortError')setSourceError(e.message)});
    return()=>controller.abort();
  },[data.id,sourceOpen,retry]);
  if(!item)return <p role="alert">未找到对应事项。<Link href={channelHref(channel)}>返回{getChannel(channel)?.name||'信息中心'}</Link></p>;
  const url=safeSourceUrl(data.document.canonical_url);
  const relevant=data.rules.filter(rule=>rule.target_id===item.cycle_id||data.items.length===1);
  const proofIds=new Set(relevant.map(r=>r.evidence_id));
  const conditions=data.evidence.filter(e=>proofIds.has(e.id)||/申请条件|报名条件|须具备|须满足|适用对象|申报条件|报名对象/.test(e.quote_or_normalized_fact)).slice(0,8);
  const materials=item.materials||[];
  const openSource=()=>{setSourceOpen(true);setTimeout(()=>sourceRef.current?.scrollIntoView({block:'nearest',behavior:'auto'}),0)};
  return <div className={styles.detail}>
    {visibleItems.length>1&&<label className={styles.itemSelect}>公告事项<select value={selected} onChange={e=>setSelected(e.target.value)}>{visibleItems.map(i=><option key={i.id} value={i.id}>{i.title}</option>)}</select></label>}
    <NoticeArtwork paths={item.paths} title={item.title} seedKey={item.id}/>
    <header className={styles.detailIntro}>
      <span className={styles.category}>{getChannel(channel)?.name||item.paths?.map(p=>p.name).join(' · ')||'公共信息'}</span>
      <h2>{item.title}</h2>
      <span className={styles.status} data-state={item.availability}>{availabilityLabels[item.availability||'']||'请核对原文'}</span>
      <dl className={styles.facts}>
        <div><dt>发布单位</dt><dd>{data.source.publisher||data.source.name}</dd></div>
        <div><dt>适用地区</dt><dd>{item.location||data.source.region_code||'原文未注明'}</dd></div>
        <div><dt>开始时间</dt><dd>{noticeDate(item.start_time)}</dd></div>
        <div><dt>截止时间</dt><dd>{noticeDate(item.deadline)}</dd></div>
      </dl>
    </header>
    <section className={styles.detailSection}><h3>公告内容</h3><p className={styles.fullText}>{item.description||'暂未提取到正文，请查看下方原文窗口。'}</p></section>
    <section className={styles.detailSection}><h3>申请条件与适用对象</h3>
      {conditions.length?<div className={styles.quotes}>{conditions.map(e=><blockquote key={e.id}><p>{e.quote_or_normalized_fact}</p><small>{e.evidence_location||'已入库原文摘录'}</small></blockquote>)}</div>:
        <p className={styles.muted}>暂未完整提取条件。原站可能限制自动访问，或条件位于附件中；请打开官方原文核对，必要时在原文资料库手动导入附件。</p>}
      {data.positions.length>0&&<details><summary>查看岗位信息（{data.positions.length}）</summary><div className={styles.positions}>{data.positions.map(p=><div key={p.id}><strong>{p.title}</strong><p>{[p.organization,p.education,p.majors].filter(Boolean).join(' · ')}</p>{p.remarks&&<p>{p.remarks}</p>}</div>)}</div></details>}
    </section>
    <section className={styles.detailSection}><h3>材料与附件</h3>{materials.length?<ul className={styles.materials}>{materials.map((m,i)=>{const link=typeof m==='object'?safeSourceUrl(m.url):undefined;return <li key={i}>{link?<a href={link} target="_blank" rel="noopener noreferrer">{typeof m==='object'?m.title:m}<Icon name="arrow" size={14}/></a>:typeof m==='object'?m.title:m}</li>})}</ul>:<p className={styles.muted}>尚未收录附件清单，以官方页面为准。<Link href="/knowledge">手动导入附件 →</Link></p>}</section>
    <section className={styles.detailSection}><h3>准备建议</h3><ul className={styles.materials}><li>核对你的年级、专业与身份是否在适用范围内。</li><li>整理原文要求的材料，区分报名时间与个人准备时间。</li><li>需要协作时进入活动组队，确认分工与投入时间。</li></ul><small className={styles.muted}>以上为准备建议，不是新增的官方报名条件。</small></section>
    <section className={styles.sourceWindow} ref={sourceRef} aria-label="原文窗口">
      <div className={styles.sectionHead}><div><h3>原文窗口</h3><small>{data.source.name} · 版本 {data.document.version_no} · 收录于 {noticeDate(data.document.fetched_at)}</small></div>
        <button type="button" onClick={()=>setSourceOpen(v=>!v)} aria-expanded={sourceOpen}>{sourceOpen?'收起文本':'阅读已收录原文'}</button></div>
      {sourceOpen&&<div className={styles.sourceText} tabIndex={0} aria-label="已收录原文文本">
        {sourceError?<div role="alert">{sourceError}<button type="button" onClick={()=>setRetry(n=>n+1)}>重试</button></div>:!source?<p role="status">正在读取原文…</p>:<><pre>{source.text||'暂未获取原文文本，请打开官方页面。'}</pre>{source.truncated&&<p>原文较长，此处显示前段；完整内容请打开官方页面。</p>}</>}
      </div>}
      {url?<a className={styles.sourceLink} href={url} target="_blank" rel="noopener noreferrer">查看官方原文（新窗口）<Icon name="arrow" size={16}/></a>:<p>当前来源没有可直接访问的网址。</p>}
    </section>
    <section className={styles.detailSection}><h3>接下来</h3><div className={styles.actions}>
      <Link className={styles.primary} href={'/agent?'+new URLSearchParams({intent:'eligibility',publication_id:data.id,item_id:item.id})}><Icon name="shield" size={16}/>核对我的资格</Link>
      <Link className={styles.secondary} href={'/teams?'+new URLSearchParams({publication:data.id,item:item.id})}><Icon name="users" size={16}/>进入活动组队</Link>
      <button type="button" onClick={openSource}>核对原文</button>
    </div><DataFollow publicationId={data.id} itemId={item.id} deadline={item.deadline}/></section>
    <DataCorrection publicationId={data.id}/>
  </div>;
}

export function NoticeDialog({publicationId,itemId,channel,onClose}:{publicationId:string;itemId:string;channel?:ChannelCode;onClose:()=>void}){
  const ref=useRef<HTMLDialogElement>(null),close=useRef<HTMLButtonElement>(null),[data,setData]=useState<Publication|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  useEffect(()=>{const dialog=ref.current,trigger=document.activeElement as HTMLElement|null;dialog?.showModal();close.current?.focus({preventScroll:true});const previous=document.body.style.overflow;document.body.style.overflow='hidden';return()=>{dialog?.close();document.body.style.overflow=previous;trigger?.focus({preventScroll:true})}},[]);
  useEffect(()=>{const controller=new AbortController();setData(null);setError('');read<Publication>('/v1/data/publications/'+encodeURIComponent(publicationId),controller.signal).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message)});return()=>controller.abort()},[publicationId,retry]);
  return <dialog ref={ref} className={styles.dialog} onCancel={onClose} onClick={e=>{if(e.target===e.currentTarget){const b=e.currentTarget.getBoundingClientRect();if(e.clientX<b.left||e.clientX>b.right||e.clientY<b.top||e.clientY>b.bottom)onClose()}}} aria-labelledby="notice-dialog-title">
    <header className={styles.dialogHead}><h2 id="notice-dialog-title">公告详情</h2><div><Link href={noticeHref(publicationId,itemId,channel)} aria-label="打开完整详情页"><Icon name="link" size={17}/></Link><button ref={close} onClick={onClose} type="button" aria-label="关闭公告详情"><Icon name="close" size={18}/></button></div></header>
    <div className={styles.dialogScroll}>{error?<div className={styles.empty} role="alert"><h3>{error}</h3><button onClick={()=>setRetry(n=>n+1)}>重新加载</button><button onClick={onClose}>返回目录</button></div>:data?<NoticeDetail data={data} itemId={itemId} channel={channel}/>:<div className={styles.loading} role="status">正在读取公告与来源…</div>}</div>
  </dialog>;
}

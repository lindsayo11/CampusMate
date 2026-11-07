'use client';

import Link from 'next/link';
import {useEffect,useRef,useState} from 'react';
import {Icon} from './ui';
import {archiveDate,evidenceRequest,externalUrl,sourceHost,WorkspaceRequestError,type SourceReading} from '@/lib/evidence-workspace';
import s from './evidence-workspace.module.css';

export function SourceReader({documentId,onClose}:{documentId:string;onClose:()=>void}){
  const dialog=useRef<HTMLDialogElement>(null);
  const [data,setData]=useState<SourceReading|null>(null),[error,setError]=useState<WorkspaceRequestError|null>(null),[retry,setRetry]=useState(0);
  useEffect(()=>{
    const previous=document.activeElement,element=dialog.current;
    element?.showModal();
    return ()=>{if(element?.open)element.close();if(previous instanceof HTMLElement&&previous.isConnected)previous.focus({preventScroll:true});};
  },[]);
  useEffect(()=>{
    const controller=new AbortController();setData(null);setError(null);
    evidenceRequest<SourceReading>('/v1/knowledge/documents/'+encodeURIComponent(documentId),{signal:controller.signal})
      .then(setData).catch(error=>{if(!controller.signal.aborted)setError(error);});
    return ()=>controller.abort();
  },[documentId,retry]);
  return <dialog ref={dialog} className={s.reader} aria-labelledby="source-reader-title" onClose={onClose}>
    <header className={s.readerHeader}><div><small>已收录原文</small><h2 id="source-reader-title">{data?.title||'阅读原文'}</h2></div><button type="button" className={s.iconButton} aria-label="关闭原文" onClick={()=>dialog.current?.close()}><Icon name="close"/></button></header>
    <div className={s.readerBody}>
      {!data&&!error&&<p role="status" className={s.empty}>正在读取已收录文本…</p>}
      {error&&<div role="alert" className={s.empty}><h3>{error.message}</h3>{error.status===401||error.status===403?<Link href="/login">重新登录</Link>:<button type="button" onClick={()=>setRetry(retry+1)}>重试</button>}</div>}
      {data&&<><div className={s.readerMeta}><span>{sourceHost(data.source_url)}</span><span>收录于 {archiveDate(data.fetched_at)}</span><span>留档 {data.character_count.toLocaleString()} 字符</span></div><p className={s.quiet}>以下为已收录正文，附件及页面后续更新请以官方原文为准。</p><div className={s.originalText}>{data.display_text??data.text}</div>{data.truncated&&<p className={s.notice}>当前显示前 12 万字符，请前往官方原文阅读完整内容。</p>}<details className={s.trace}><summary>版本与引用定位</summary><p>文档：{data.document_id}</p><p>原始留档 SHA-256：{data.content_hash}</p><p>{data.chunk_count} 段可检索文本</p>{data.is_formatted&&<details><summary>查看原始留档</summary><div className={s.originalText}>{data.text}</div></details>}</details></>}
    </div>
    {data&&<footer className={s.readerFooter}><span>原文留档 · 保留来源</span><div>{data.opportunity_id&&<Link href={'/eligibility?opportunity_id='+encodeURIComponent(data.opportunity_id)}>核对我的资格<Icon name="shield" size={15}/></Link>}{externalUrl(data.source_url)&&<a className={s.primary} href={externalUrl(data.source_url)} target="_blank" rel="noreferrer">打开官方原文<Icon name="link" size={15}/></a>}</div></footer>}
  </dialog>;
}

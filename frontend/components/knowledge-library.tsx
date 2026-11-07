'use client';
import Link from 'next/link';
import {useEffect,useRef,useState} from 'react';
import {Icon} from './ui';
import {SourceReader} from './source-reader';
import type {Citation} from './source-citations';
import {archiveDate,evidenceRequest,externalUrl,sourceHost,sourceTypes,WorkspaceRequestError,type SourceDirectory} from '@/lib/evidence-workspace';
import {pageNumbers} from '@/lib/pagination';
import s from './evidence-workspace.module.css';

type SearchResult={items:Citation[];message:string;candidate_limit_reached:boolean};
export function KnowledgeLibrary({initialDocument}:{initialDocument?:string}){
  const [directory,setDirectory]=useState<SourceDirectory|null>(null),[kind,setKind]=useState(''),[offset,setOffset]=useState(0);
  const [query,setQuery]=useState(''),[searched,setSearched]=useState(''),[results,setResults]=useState<SearchResult|null>(null);
  const [busy,setBusy]=useState(true),[searching,setSearching]=useState(false),[error,setError]=useState<WorkspaceRequestError|null>(null),[retry,setRetry]=useState(0);
  const [documentId,setDocumentId]=useState<string|null>(initialDocument||null);
  const request=useRef<AbortController|null>(null);
  useEffect(()=>{
    const controller=new AbortController();setBusy(true);setError(null);
    evidenceRequest<SourceDirectory>('/v1/knowledge/documents?offset='+offset+'&limit=9'+(kind?'&kind='+encodeURIComponent(kind):''),{signal:controller.signal})
      .then(setDirectory).catch(error=>{if(!controller.signal.aborted)setError(error);}).finally(()=>{if(!controller.signal.aborted)setBusy(false);});
    return ()=>controller.abort();
  },[kind,offset,retry]);
  useEffect(()=>()=>request.current?.abort(),[]);
  async function search(value:string){
    if(value.trim().length<2){setError(new WorkspaceRequestError('请输入至少两个字的关键词',422));return;}
    request.current?.abort();const controller=new AbortController();request.current=controller;
    setQuery(value);setSearching(true);setError(null);setSearched(value.trim());setResults(null);
    try{setResults(await evidenceRequest<SearchResult>('/v1/knowledge/search',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({query:value.trim(),type:kind||null,limit:10})}));}
    catch(error){if(!controller.signal.aborted)setError(error as WorkspaceRequestError);}
    finally{if(!controller.signal.aborted)setSearching(false);}
  }
  function browse(nextKind=kind){request.current?.abort();setSearching(false);setSearched('');setResults(null);setQuery('');setError(null);setKind(nextKind);setOffset(0);if(!directory&&nextKind===kind&&offset===0)setRetry(value=>value+1);}
  const pages=Math.ceil((directory?.total||0)/9),current=Math.floor(offset/9)+1;
  return <div className={s.page}>
    <header className={s.heading}><div><span className={s.titleIcon}><Icon name="book" size={23}/></span><div><h1>查找原文依据</h1><p>从资料到出处，把重要条件看清楚。</p></div></div><Link href="/eligibility">核对我的资格<Icon name="arrow" size={16}/></Link></header>
    <div className={s.libraryBar}><div><strong>{directory?.library_total??'—'}</strong><span>份公开资料</span></div><div><strong>{directory?.chunk_total??'—'}</strong><span>段可检索原文</span></div><div><Icon name="link" size={19}/><span>每条资料均保留来源</span></div></div>
    <section className={s.searchArea} aria-label="检索原文">
      <form className={s.searchForm} onSubmit={event=>{event.preventDefault();void search(query);}}>
        <label className={s.searchInput}><Icon name="search"/><input aria-label="要查找的内容" placeholder="搜索院校、公告或条件关键词…" value={query} maxLength={200} onChange={event=>setQuery(event.target.value)}/></label>
        <select aria-label="资料板块" value={kind} onChange={event=>browse(event.target.value)}><option value="">全部板块</option>{Object.entries(directory?.by_type||{}).sort((a,b)=>b[1]-a[1]).map(([type,count])=><option key={type} value={type}>{sourceTypes[type]||'其他资料'} · {count}</option>)}</select>
        <button className={s.primary} disabled={searching} type="submit">{searching?'检索中…':'检索依据'}<Icon name="arrow" size={15}/></button>
      </form>
      <div className={s.quickSearch}><span>常用检索</span>{['报名材料','申请条件','截止时间','推免','竞赛'].map(text=><button type="button" key={text} onClick={()=>void search(text)} disabled={searching}>{text}</button>)}</div>
    </section>
    <div className={s.sectionTitle}><div><h2>{searched?'相关原文片段':'已收录资料'}</h2><span role="status">{searched?'“'+searched+'”'+(results?' · '+results.items.length+' 条片段':''):(kind?sourceTypes[kind]||'其他资料':'全部板块')+(!busy&&!error&&directory?' · '+directory.total+' 份':'')}</span></div>{searched?<button type="button" onClick={()=>browse()}>返回资料目录<Icon name="arrow" size={14}/></button>:<button type="button" aria-label="刷新资料目录" disabled={busy} onClick={()=>setRetry(retry+1)}><Icon name="refresh" size={15}/>刷新</button>}</div>
    {error&&<div role="alert" className={s.notice}><span>{error.message}</span>{error.status===401||error.status===403?<Link href="/login">去登录</Link>:<button type="button" onClick={()=>searched?void search(query):setRetry(retry+1)}>重试</button>}</div>}
    {(searched?searching:busy)&&<div className={s.loading} role="status"><Icon name="clock"/>正在整理资料…</div>}
    {searched?results&&<div className={s.citations}>
      {results.items.length===0?<div className={s.empty}><Icon name="search" size={26}/><h3>未找到对应原文片段</h3><p>换一个院校或条件关键词，也可以直接浏览资料目录。</p><button onClick={()=>browse('')}>浏览全部资料</button></div>:results.items.map(item=><article className={s.citation} key={item.chunk_id}>
        <div className={s.cardMeta}><span>{sourceHost(item.source_url)}</span><span>收录于 {archiveDate(item.fetched_at)}</span></div><h3>{item.title}</h3><blockquote>{item.text}</blockquote>
        <footer><button type="button" onClick={()=>setDocumentId(item.document_id)}>阅读已收录原文<Icon name="book" size={15}/></button>{externalUrl(item.source_url)&&<a href={externalUrl(item.source_url)} target="_blank" rel="noreferrer">官方原文<Icon name="link" size={14}/></a>}<small>字符 {item.start_offset}—{item.end_offset}</small></footer>
      </article>)}
      {results.candidate_limit_reached&&<p className={s.quiet}>匹配较多，请增加关键词或选择板块缩小范围。</p>}
    </div>:<section className={s.documentGrid} aria-label="资料目录" aria-busy={busy}>
      {!busy&&!error&&directory?.items.map(item=><article className={s.documentCard} key={item.document_id}>
        <div className={s.cardMeta}><span className={s.documentIcon}><Icon name="file" size={24}/></span><span>{sourceTypes[item.type]||'参考资料'}</span><small>{item.chunk_count} 段原文</small></div>
        <h3><button type="button" onClick={()=>setDocumentId(item.document_id)}>{item.title||'已收录资料'}</button></h3><p className={s.excerpt}>{item.excerpt}</p>
        <div className={s.archiveMeta}><span>{sourceHost(item.source_url)}</span><time>{archiveDate(item.fetched_at)}</time></div>
        <footer><button type="button" onClick={()=>setDocumentId(item.document_id)}>阅读原文<Icon name="arrow" size={15}/></button>{externalUrl(item.source_url)&&<a href={externalUrl(item.source_url)} target="_blank" rel="noreferrer" aria-label={'打开官方原文：'+item.title}><Icon name="link" size={16}/></a>}</footer>
      </article>)}
      {!busy&&directory?.items.length===0&&<div className={s.empty}><h3>这个板块暂无公开资料</h3><p>未公开、已撤回的版本不会在这里展示。</p><button onClick={()=>browse('')}>查看全部板块</button></div>}
    </section>}
    {!searched&&!error&&pages>1&&<nav className={s.pagination} aria-label="资料分页"><button aria-label="上一页" disabled={busy||current===1} onClick={()=>setOffset(offset-9)}>‹</button>{pageNumbers(current,pages).map((page,index)=>page==='ellipsis'?<span key={'gap'+index}>…</span>:<button key={page} aria-label={'第 '+page+' 页'} aria-current={page===current?'page':undefined} disabled={busy} onClick={()=>setOffset((page-1)*9)}>{page}</button>)}<button aria-label="下一页" disabled={busy||current===pages} onClick={()=>setOffset(offset+9)}>›</button></nav>}
    <aside className={s.bottomNote}><Icon name="shield" size={18}/><p>未找到关键附件？部分官网有反爬或登录限制，请在官网下载 PDF、Word 或 Excel 后，交由管理员导入核验。</p><Link href="/data">浏览信息中心<Icon name="arrow" size={14}/></Link></aside>
    {documentId&&<SourceReader documentId={documentId} onClose={()=>setDocumentId(null)}/>}
  </div>;
}

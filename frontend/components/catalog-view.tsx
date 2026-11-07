import Link from 'next/link';
import {privateApi} from '@/lib/session-api';
import {Icon,streams} from '@/components/ui';
import {ManualRefreshButton} from '@/components/manual-refresh-button';
import {NoticeGrid} from '@/components/notice-grid';
import {Pagination} from '@/components/pagination';
import type {CatalogPage} from '@/lib/catalog';
import {catalogHref,channelHref,type CatalogFilters,type DevelopmentChannel} from '@/lib/development-channels';
import styles from '@/components/explore.module.css';

type ChannelSummary={overview:string;sections:{title:string;bullets:string[]}[];source_count:number;error?:string};
export async function CatalogView({filters,channel}:{filters:CatalogFilters;channel?:DevelopmentChannel}){
  const p={...filters,path:channel?.code||(filters.path==='entrepreneurship'?'entrepreneurship':'')};
  const limit=12,rawOffset=Number(p.offset),offset=Number.isFinite(rawOffset)?Math.max(0,Math.floor(rawOffset)):0;
  const status=['active','expired','all'].includes(p.status||'')?p.status!:'all';
  const kind=['application_notice','reference','news_report'].includes(p.kind||'')?p.kind!:'all';
  const sort=p.sort==='deadline'?'deadline':'recent';
  const year=/^20\d{2}$/.test(p.year||'')?p.year!:'';
  const query=new URLSearchParams({q:p.q||'',offset:String(offset),limit:String(limit),status,kind,sort});
  for(const [key,value] of Object.entries({path:p.path,region:p.region,school:p.school,year}))if(value)query.set(key,value);
  const [data,summary]:[CatalogPage,ChannelSummary|null]=await Promise.all([
    privateApi('/v1/data/catalog?'+query),
    p.path?privateApi('/v1/data/channel-summary?path='+encodeURIComponent(p.path)).catch(()=>({overview:'',sections:[],source_count:0,error:'unavailable'})):Promise.resolve(null),
  ]);
  const href=(changes:Record<string,string>)=>catalogHref(channel?.code,{...Object.fromEntries(query),...changes});
  return <div className={styles.surface} data-channel={channel?.code}>
    <header className={styles.heading}><div><h1>{channel?.name||streams.find(s=>s.code===p.path)?.name||'信息中心'}</h1><p>{channel?.description||'找到值得关注的机会，也看清每一条信息的来源。'}</p></div><div className={styles.actions}><Link className={styles.secondary} href="/data/timeline"><Icon name="calendar" size={16}/>发展日历</Link><ManualRefreshButton/></div></header>
    <form action={channelHref(channel?.code)} role="search" aria-label={channel?channel.name+'频道搜索':'信息中心搜索'}>
      <div className={styles.toolbar}><label className={styles.search}><Icon name="search" size={19}/><input name="q" aria-label="搜索公告、关键词" defaultValue={p.q} placeholder={channel?.searchPlaceholder||'搜索公告、赛事或院校'} maxLength={100}/></label>
        <select name="status" aria-label="信息状态" defaultValue={status}><option value="all">所有状态</option><option value="active">当前信息</option><option value="expired">已截止</option></select>
        <select name="sort" aria-label="信息排序" defaultValue={sort}><option value="recent">最近发布</option><option value="deadline">临近截止</option></select>
        <button className={styles.primary} type="submit"><Icon name="filter" size={16}/>筛选</button>
      </div>
      {!channel&&p.path&&<input type="hidden" name="path" value={p.path}/>}
      <details className={styles.filterMore}><summary>更多筛选</summary><div className={styles.filterFields}>
        <label>目标高校<input name="school" defaultValue={p.school} placeholder="全部高校" maxLength={120}/></label>
        <label>通知年份<input type="number" name="year" min={2000} max={2099} defaultValue={year} placeholder="全部年份"/></label>
        <label>地区代码<input name="region" defaultValue={p.region} placeholder="例如 CN-GD" maxLength={80}/></label>
        <label>信息类型<select name="kind" defaultValue={kind}><option value="all">全部类型</option><option value="application_notice">招生与申请通知</option><option value="reference">政策与参考资料</option><option value="news_report">新闻与活动报道</option></select></label>
      </div></details>
    </form>
    {!channel&&<nav className={styles.tabs} aria-label="信息频道"><Link href={href({path:'',offset:'0'})} aria-current={!p.path?'page':undefined}>全部信息</Link>{streams.map(s=><Link key={s.code} href={channelHref(s.code)}>{s.name}</Link>)}</nav>}
    {summary?.error&&!summary.overview&&<p className={styles.muted} role="status">频道摘要暂时不可用，仍可浏览下方公告。</p>}
    {summary?.overview&&<details className={styles.channelSummary}><summary>本频道资料摘要 · {summary.source_count} 份来源</summary><p>{summary.overview}</p>{summary.sections?.map((s,i)=><div key={i}><h3>{s.title}</h3><ul>{s.bullets.map((b,n)=><li key={n}>{b}</li>)}</ul></div>)}<small>内容归纳供参考，具体条件以原文为准。</small></details>}
    <div className={styles.sectionHead}><span>展示 <b>{data.items.length?offset+1:0}–{data.items.length?Math.min(offset+data.items.length,data.total):0}</b> / {data.total} 条信息</span>{(p.q||p.school||p.region||year||kind!=='all'||status!=='all')&&<Link href={href({q:'',school:'',region:'',year:'',kind:'all',status:'all',offset:'0'})}>清除筛选</Link>}</div>
    {data.items.length?<NoticeGrid items={data.items} channel={channel?.code}/>:<div className={styles.empty}><h3>没有找到匹配的信息</h3><Link href={href({q:'',school:'',region:'',year:'',kind:'all',status:'all',offset:'0'})}>{channel?'清除筛选，查看本频道信息':'清除筛选，查看全部'}</Link></div>}
    <Pagination label="信息分页" total={data.total} limit={limit} offset={offset} href={value=>href({offset:String(value)})}/>
  </div>;
}

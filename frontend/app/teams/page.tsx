import Link from 'next/link';
import {privateApi} from '@/lib/session-api';
import CommunicationSpace from '@/components/communication-space';
import {ActivityTeams} from '@/components/activity-teams';
import {NoticeArtwork} from '@/components/notice-artwork';
import {Pagination} from '@/components/pagination';
import {Icon,streams} from '@/components/ui';
import type {CatalogItem} from '@/lib/catalog';
import {noticeSummary,teamLabels} from '@/lib/explore';
import styles from '@/components/explore.module.css';
type Filters={q?:string;path?:string;state?:string;offset?:string;publication?:string;item?:string;room?:string;view?:string};
type Activity=CatalogItem&{team_state:string;team_count:number;open_slots:number};
export default async function Teams({searchParams}:{searchParams:Promise<Filters>}){
 const p=await searchParams;
 if(p.room||p.view==='messages')return <><div style={{padding:'20px 32px 0'}}><Link href="/teams">← 返回团队空间</Link></div><CommunicationSpace/></>;
 if(p.publication&&p.item)return <ActivityTeams key={p.publication+p.item} publicationId={p.publication} itemId={p.item}/>;
 const limit=12,offset=Math.max(0,Math.floor(Number(p.offset)||0)),state=['none','recruiting','full','closed','joined'].includes(p.state||'')?p.state!:'all';
 const query=new URLSearchParams({q:p.q||'',path:p.path||'',state,offset:String(offset),limit:String(limit)});
 const data:{total:number;items:Activity[]}=await privateApi('/v1/activity-teams/directory?'+query);
 const href=(changes:Record<string,string>)=>'/teams?'+new URLSearchParams({...Object.fromEntries(query),...changes});
 return <div className={styles.surface}><header className={styles.heading}><div><h1>团队空间</h1><p>围绕同一件事，找到一起行动的人。</p></div><div className={styles.actions}><Link className={styles.secondary} href="/teams?view=messages">我的会话</Link><Link className={styles.primary} href="/team-manager"><Icon name="users" size={16}/>我的团队</Link></div></header>
  <form className={styles.toolbar} action="/teams"><label className={styles.search}><Icon name="search" size={18}/><input name="q" aria-label="搜索组队活动" placeholder="搜索活动、竞赛或公告" defaultValue={p.q} maxLength={100}/></label>
   <select name="path" aria-label="组队发展路径" defaultValue={p.path||''}><option value="">全部方向</option>{streams.map(s=><option key={s.code} value={s.code}>{s.name}</option>)}</select>
   <select name="state" aria-label="组队状态" defaultValue={state}><option value="all">所有组队状态</option>{Object.entries(teamLabels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select>
   <button className={styles.primary}>筛选<Icon name="filter" size={15}/></button>
  </form>
  <div className={styles.sectionHead}><h2>组队目录</h2><span>共 <b>{data.total}</b> 项</span></div>
  <div className={styles.directory}>{data.items.map(item=><article className={styles.directoryRow} key={item.id}>
   <div className={styles.directoryThumb}><NoticeArtwork paths={item.paths} title={item.title} seedKey={item.id}/></div>
   <div><h2>{item.title}</h2><p>{noticeSummary(item)}</p><span className={styles.status} data-state={item.team_state}>{teamLabels[item.team_state]}{item.team_count?' · '+item.team_count+' 支队伍':''}{item.open_slots?' · 余 '+item.open_slots+' 个名额':''}</span></div>
   <Link href={'/teams?'+new URLSearchParams({publication:item.publication_id,item:item.id})}>查看组队<Icon name="chevron" size={16}/></Link>
  </article>)}</div>
  {!data.items.length&&<div className={styles.empty}><h3>暂无符合筛选的活动</h3><Link href="/teams">查看全部目录</Link></div>}
  <Pagination label="组队目录分页" total={data.total} limit={limit} offset={offset} href={value=>href({offset:String(value)})}/>
 </div>;
}

import Link from 'next/link';
import {OpportunityCard} from '@/components/opportunity-card';
import {getOpportunities} from '@/lib/api';
import {optionalWorkspaceApi} from '@/lib/workspace';
import {NoticeGrid} from '@/components/notice-grid';
import styles from '@/components/explore.module.css';
import type {CatalogPage} from '@/lib/catalog';
import {EmptyState,Icon,PageHeading} from '@/components/ui';
const labels:Record<string,string>={job:'实习就业',contest:'竞赛项目',civil_service:'考公考编',volunteer:'志愿活动',club:'社团活动',graduate:'升学机会'};
export default async function Opportunities({searchParams}:{searchParams:Promise<{type?:string;q?:string;status?:string}>}){
 const p=await searchParams;const [data,routed]=await Promise.all([getOpportunities(p.type,p.q,p.status),optionalWorkspaceApi('/v1/data/catalog?limit=12&status=active&kind=application_notice') as Promise<CatalogPage|null>]);
 return <div className={styles.surface}><PageHeading title={p.type?labels[p.type]||'校园机会':'校园机会'}><Link className="button secondary" href="/tracker"><Icon name="check" size={15}/>我的行动</Link></PageHeading>
  <div className="tabs opportunities-tabs"><Link className={!p.type?'active':''} href="/opportunities">全部机会</Link>{Object.entries(labels).map(([k,v])=><Link className={p.type===k?'active':''} href={'/opportunities?'+new URLSearchParams({type:k,q:p.q||'',status:p.status||'active'})} key={k}>{v}</Link>)}</div>
  <form className={styles.opportunityFilters} action="/opportunities"><input type="hidden" name="type" value={p.type||''}/><div className={styles.search}><Icon name="search" size={17}/><input name="q" aria-label="搜索校园机会" defaultValue={p.q} placeholder="搜索名称、组织或关键词…"/></div><select name="status" aria-label="机会状态" defaultValue={p.status||'active'}><option value="active">未截止</option><option value="expired">已截止</option><option value="all">全部状态</option></select><button className={styles.primary}>筛选</button></form>
  <div className="list-summary"><span>找到 <b>{data.total}</b> 个机会</span><Link href="/data">查找发展政策与院校信息 →</Link></div><div className={styles.grid}>{data.items.map(item=><OpportunityCard key={item.id} item={item}/>)}</div>{!data.total&&<EmptyState title="还没有匹配的机会" description="调整关键词或切换状态，看看其他值得关注的内容。" href="/opportunities?status=all" label="查看全部机会"/>}
  {!p.type&&Boolean(routed?.items.length)&&<section><div className={styles.sectionHead}><h2>六大路线 · 官方新机会</h2><Link href="/data?kind=application_notice">查看全部通知 →</Link></div><NoticeGrid items={routed!.items}/></section>}
 </div>
}

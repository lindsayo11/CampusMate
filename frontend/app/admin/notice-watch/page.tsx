import Link from 'next/link';
import {privateApi} from '@/lib/session-api';
import {NoticeWatchControls} from '@/components/notice-watch-controls';
import {PageHeading} from '@/components/ui';
type Source={endpoint_id:string;name:string;enabled:boolean;columns:string[];last_checked:string|null;index_healthy:boolean;discovered:number;collected:number;issues:number};
type Resource={id:string;url:string;title:string;kind:string;status:string;error:string;next_check_at:string};
export default async function NoticeWatchPage(){
 const data:{enabled:boolean;sources:Source[];resources:Resource[]}=await privateApi('/v1/admin/notice-watch');
 return <div className="shell"><Link className="back" href="/admin/data">← 数据工作台</Link><PageHeading eyebrow="持续采集" title="官方栏目监测" description="后台自动发现新通知并重查正文。异常记录保留在队列中，其他来源继续运行。"/>
 <p>采集服务{data.enabled?'已启用':'未启用'} · 栏目每 12 小时检查 · 正文每 24 小时重查</p>
 <div className="coverage-summary watch-cards">{data.sources.map(s=><section className="card" key={s.endpoint_id}><h2>{s.name}</h2><p>{!s.enabled?'已暂停':s.index_healthy?'栏目检查正常':'等待检查或需要处理'} · 发现 {s.discovered} · 已解析 {s.collected} · 异常 {s.issues}</p><details><summary>官方栏目</summary>{s.columns.map(url=><p key={url}><a href={url} target="_blank" rel="noreferrer">{url}</a></p>)}</details><NoticeWatchControls id={s.endpoint_id} enabled={s.enabled}/></section>)}</div>
 <h2>待处理与异常</h2>{data.resources.filter(r=>r.error||r.status==='queued'||r.status==='attachments_pending').map(r=><section className="card" key={r.id}><a href={r.url} target="_blank" rel="noreferrer">{r.title||r.url}</a><p>{r.error|| (r.status==='attachments_pending'?'已发现 PDF 附件，单独跟踪解析状态':'已发现，等待后台采集')}</p><small>下次检查 {new Date(r.next_check_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}</small></section>)}
 </div>
}

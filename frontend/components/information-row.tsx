import Link from 'next/link';
import type {CatalogItem} from '@/lib/catalog';
import {dateLabel, Icon, streams} from '@/components/ui';

export function InformationRow({item}:{item:CatalogItem}) {
  const deadline = item.deadline ? new Date(item.deadline).getTime() : NaN;
  const expired = Number.isFinite(deadline) && deadline <= Date.now();
  const soon = Number.isFinite(deadline) && !expired && deadline - Date.now() <= 7 * 86400000;
  const pathName = (code:string, name:string) => streams.find(s => s.code === code)?.name || name;
  const location = /^\d+$/.test(item.location) ? '' : item.location;
  const sourceLabel = item.document.import_mode === 'demo' ? '模拟数据' : item.document.import_mode === 'system' ? '系统导入' : '审核发布';
  return <article className="feed-row information-row">
    <div className="information-content">
      <div className="feed-meta"><span className="source-avatar"><Icon name="file" size={14}/></span><b>{item.source.name}</b><span className={`source-label ${item.document.import_mode === 'demo' ? 'demo-label' : ''}`}>{sourceLabel}</span></div>
      <h3><Link href={'/data/' + item.publication_id}>{item.title}</Link></h3>
      <p className="information-excerpt">{item.description.length > 220 ? item.description.slice(0,220) + '…' : item.description || '查看详情，核对通知内容和来源。'}</p>
      <div className="information-bottom"><div className="tagrow">
        {item.content_kind&&<span>{({application_notice:'招生与申请通知',reference:'参考资料',news_report:'新闻报道'} as Record<string,string>)[item.content_kind]}</span>}{item.availability&&!['reference','report'].includes(item.availability)&&<span className={item.availability==='expired'?'is-expired':''}>{({open:'报名窗口内',upcoming:'尚未开始',expired:'已截止',needs_confirmation:'时间待核对',reference:'参考资料',report:'活动报道'} as Record<string,string>)[item.availability]}</span>}
        {item.paths.map(p => <span key={p.code}>{pathName(p.code, p.name)}</span>)}
        {location && <span>{location}</span>}
        <span className={`deadline-label ${soon ? 'is-soon' : ''} ${expired ? 'is-expired' : ''}`}><Icon name="clock" size={12}/>{expired ? '已截止 · ' : item.deadline ? '截止 · ' : ''}{item.deadline ? dateLabel(item.deadline) : '截止时间以原文为准'}</span>
      </div><Link className="information-open" href={'/data/' + item.publication_id}>详情与原文依据<Icon name="arrow" size={14}/></Link></div>
      {item.document.fetched_at && <small className="information-collected">{item.document.publish_time?'发布于 '+dateLabel(item.document.publish_time)+' · ':'发布时间未识别 · '}采集于 {dateLabel(item.document.fetched_at)} · 申请前请核对原文</small>}
    </div>
  </article>;
}

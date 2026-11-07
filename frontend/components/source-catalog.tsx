'use client';

import {useState} from 'react';
import {discoveryLabel} from '@/lib/source-discovery';

type CatalogSource = {code:string;name:string;topic:string;topic_label:string;region:string;status:string;index_urls:string[];discovery_format?:string;index_formats?:Record<string,string>;checked_at:string|null;error:string;installed:boolean;enabled:boolean};
export type SourceCatalogData = {total:number;checked_at:string|null;statuses:Record<string,number>;topics:{topic:string;label:string;total:number;ready:number}[];sources:CatalogSource[]};
const statusLabels:Record<string,string> = {ready:'正文抽样通过',index_ready:'正文待适配',blocked:'访问或结构受阻',candidate:'待探测'};

export function SourceCatalog({data}:{data:SourceCatalogData}) {
  const [topic,setTopic] = useState('all');
  const [status,setStatus] = useState('all');
  const [query,setQuery] = useState('');
  const entries = data.sources.filter(s=>(topic==='all'||s.topic===topic)&&(status==='all'||s.status===status)&&`${s.name} ${s.region} ${s.code}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <section className="topic-section">
    <h2>信息源目录 · {data.total} 个候选</h2>
    <p>正文抽样通过 {data.statuses.ready||0} 个 · 正文待适配 {data.statuses.index_ready||0} 个 · 访问或结构受阻 {data.statuses.blocked||0} 个。抽样通过表示能读取部分正文，实际运行状态以上方监测结果为准。</p>
    <p>公开栏目覆盖考研、推免、教育考试、招聘、就业、留学、奖学金及创业竞赛。每个来源仅覆盖列出的栏目；页面可访问不等于已获得转载许可。</p>
    <div className="notice-filter-grid source-catalog-filters">
      <label>搜索来源 <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="学校、机构或地区代码"/></label>
      <label>信息类型 <select value={topic} onChange={e=>setTopic(e.target.value)}><option value="all">全部类型</option>{data.topics.map(t=><option key={t.topic} value={t.topic}>{t.label}（{t.ready}／{t.total} 抽样通过）</option>)}</select></label>
      <label>探测结果 <select value={status} onChange={e=>setStatus(e.target.value)}><option value="all">全部结果</option>{Object.entries(statusLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
    </div>
    <p>显示 {entries.length} 个来源</p>
    <div className="coverage-table-wrap"><table className="coverage-table"><thead><tr><th>来源</th><th>类型／地区</th><th>探测与运行</th><th>官方栏目及问题</th></tr></thead><tbody>{entries.map(s=><tr key={s.code}>
      <td>{s.name}<p className="form-help">{s.code}</p></td><td>{s.topic_label}<p className="form-help">{s.region}</p></td>
      <td>{statusLabels[s.status]||s.status}<p className="form-help">{s.enabled?'监测开启':s.installed?'监测暂停':'尚未安装监测'}</p></td>
      <td>{s.index_urls.map((url,i)=><p key={url}><a href={url} target="_blank" rel="noreferrer">{discoveryLabel(s,url)} {i+1} ↗</a></p>)}{s.error&&<p className="form-help">{s.error}</p>}</td>
    </tr>)}</tbody></table>{entries.length===0&&<p>没有符合筛选条件的来源。</p>}</div>
  </section>;
}

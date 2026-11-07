import Link from 'next/link';
import {privateApi} from '@/lib/session-api';
import {ContextRail,EmptyState,Icon,PageHeading,TopicBar,streams} from '@/components/ui';
import {InformationRow} from '@/components/information-row';
import type {CatalogPage,PathRecord} from '@/lib/catalog';
type Filters={q?:string;path?:string;region?:string;offset?:string;status?:string;school?:string;year?:string;kind?:string;sort?:string};
const schools=['北京大学','清华大学','复旦大学','上海交通大学','浙江大学','中国科学技术大学','西安交通大学','电子科技大学'];
export default async function DataPage({searchParams}:{searchParams:Promise<Filters>}){
  const p=await searchParams;
  const offset=Math.max(0,Math.floor(Number(p.offset)||0));
  const status=['active','expired','all'].includes(p.status||'')?p.status!:'active';
  const kind=['application_notice','reference','news_report'].includes(p.kind||'')?p.kind!:'all';
  const sort=p.sort==='deadline'?'deadline':'recent';
  const year=/^20\d{2}$/.test(p.year||'')?p.year!:'';
  const query=new URLSearchParams({q:p.q||'',offset:String(offset),limit:'20',status,kind,sort});
  for(const [key,value] of Object.entries({path:p.path,region:p.region,school:p.school,year}))if(value)query.set(key,value);
  const [data,paths]:[CatalogPage,PathRecord[]]=await Promise.all([privateApi('/v1/data/catalog?'+query),privateApi('/v1/paths')]);
  const stream=streams.find(s=>s.code===p.path),selected=paths.find(s=>s.code===p.path);
  const href=(changes:Record<string,string>)=>'/data?'+new URLSearchParams({...Object.fromEntries(query),...changes});
  const filtered=Boolean(p.q||p.region||p.school||year||kind!=='all'),emptyChannel=Boolean(p.path&&!filtered&&!data.total);
  const clear=href({q:'',region:'',school:'',year:'',kind:'all',offset:'0'});
  return <div className="shell information-shell">
    <PageHeading eyebrow={stream?'我的发展方向':'发现与准备'} title={stream?.name||selected?.name||'发展信息中心'} description={stream?.note||'找到感兴趣的信息，核对来源，再加入你的准备计划。'}><Link className="button secondary" href="/data/timeline"><Icon name="calendar" size={16}/>事项时间线</Link>{p.path==='entrepreneurship'&&<Link className="button primary" href="/startup"><Icon name="spark" size={16}/>进入创业工作台</Link>}</PageHeading>
    <nav className="channel-pills" aria-label="切换发展频道"><Link className={!p.path?'active':''} aria-current={!p.path?'page':undefined} href={href({path:'',offset:'0'})}>全部方向</Link>{streams.map(s=><Link key={s.code} className={p.path===s.code?'active':''} aria-current={p.path===s.code?'page':undefined} href={href({path:s.code,offset:'0'})}>{s.name}</Link>)}</nav>
    <div className="workspace-columns"><div>
      <form key={JSON.stringify(p)} className="filter-bar information-filters" action="/data">
        <label className="filter-query"><span className="sr-only">搜索信息</span><Icon name="search" size={17}/><input name="q" aria-label="搜索信息" defaultValue={p.q} placeholder="搜索通知、岗位或政策关键词" maxLength={100}/></label>
        <button className="primary">筛选信息</button>
        <div className="notice-filter-grid"><label>目标高校<input name="school" list="target-schools" defaultValue={p.school} placeholder="全部高校" maxLength={120}/><datalist id="target-schools">{schools.map(s=><option key={s} value={s}/>)}</datalist></label><label>通知年份<input type="number" name="year" min={2000} max={2099} placeholder="如 2027" defaultValue={year}/></label><label>信息类型<select name="kind" defaultValue={kind}><option value="all">全部类型</option><option value="application_notice">招生与申请通知</option><option value="reference">政策与参考资料</option><option value="news_report">新闻与活动报道</option></select></label><label>排序<select name="sort" defaultValue={sort}><option value="recent">优先最近发布</option><option value="deadline">优先临近截止</option></select></label></div>
        <details className="advanced-filters" open={Boolean(p.region)}><summary><Icon name="filter" size={15}/>路径与地区</summary><div><label>发展路径<select name="path" defaultValue={p.path||''}><option value="">全部发展路径</option>{paths.filter(x=>x.code).map(x=><option value={x.code!} key={x.id}>{streams.find(s=>s.code===x.code)?.name||x.name}</option>)}</select></label><label>地区代码<input name="region" defaultValue={p.region} placeholder="如 CN-GD 或 320000"/></label><small>使用来源标注的地区代码。</small></div></details>
        <input type="hidden" name="status" value={status}/>
      </form>
      <div className="information-toolbar"><nav className="tabs" aria-label="信息有效期">{[['active','当前资料'],['all','全部信息'],['expired','已截止']].map(([value,label])=><Link key={value} className={status===value?'active':''} aria-current={status===value?'page':undefined} href={href({status:value,offset:'0'})}>{label}</Link>)}</nav><span className="result-count">{data.total} 条信息{Boolean(data.merged_items)&&` · 已合并 ${data.merged_items} 条同文`}</span></div>
      {filtered&&<div className="active-filters"><span>筛选结果{p.school&&` · ${p.school}`}{year&&` · ${year} 年`}{p.q&&` · “${p.q}”`}</span><Link href={clear}>清除筛选<Icon name="close" size={12}/></Link></div>}
      <section className="topic-section"><TopicBar title={stream?.name||selected?.name||'全部发展信息'}><span>{sort==='deadline'?'按截止时间':'按发布时间 · 未识别日期按收录时间'}</span></TopicBar>{data.items.map(item=><InformationRow key={item.id} item={item}/>)}
        {!data.items.length&&<EmptyState icon={emptyChannel?'book':'search'} title={emptyChannel?'这个方向的内容仍在补充':'没有找到匹配的信息'} description={kind==='news_report'&&status==='active'?'新闻报道不出现在当前资料中，请切换“全部信息”。':'结果只覆盖平台已收录的信息；试着减少条件，或查看已截止的历史通知。'} href={emptyChannel?'/paths?path='+p.path:clear} label={emptyChannel?'了解准备路径':'清除筛选'}/>}
      </section>
      {data.total>0&&<nav className="pagination" aria-label="信息分页">{offset>0&&<Link className="button secondary" href={href({offset:String(Math.max(0,offset-20))})}>上一页</Link>}<span>第 {offset+1}–{Math.min(offset+data.items.length,data.total)} 条 · 共 {data.total} 条</span>{offset+20<data.total&&<Link className="button secondary" href={href({offset:String(offset+20)})}>下一页</Link>}</nav>}
    </div><ContextRail>
      <section className="rail-tip"><span className="assistant-mark"><Icon name="check" size={22}/></span><h3>让信息变成下一步</h3><ol className="information-steps"><li><span>1</span>查看通知和官方原文</li><li><span>2</span>核对时间与申请条件</li><li><span>3</span>加入计划，拆成材料清单</li></ol><Link className="section-link" href="/tracker">查看我的计划<Icon name="arrow" size={14}/></Link></section>
      {p.path==='entrepreneurship'?<section><h2>从政策信息到创业执行</h2><p>创建项目资料，设计商业模式，测算资金与股权，再迭代 BP 和协议草稿。政策信息用于核对支持条件。</p><Link className="section-link" href="/startup">打开创业工作台<Icon name="arrow" size={14}/></Link></section>:<section><h2>覆盖哪些高校？</h2><p>首批重点补充全国主要高校考研与推免通知。部分内容仅覆盖院系，不代表整所学校的全部机会。</p><Link className="section-link" href="/data/coverage">查看实际覆盖与更新时间<Icon name="arrow" size={14}/></Link></section>}
      <section><h2>怎么理解这些信息？</h2><p>“当前资料”包含截止时间尚未识别的通知，不能据此判断仍可报名。新闻报道仅在“全部信息”展示。</p><p>通知年份来自标题，可能是招生年度或发布年度。系统导入未经人工逐条审核，申请条件以原文为准。</p></section>
    </ContextRail></div>
  </div>;
}

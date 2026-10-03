import Link from 'next/link';
import {optionalWorkspaceApi} from '@/lib/workspace';
import {ContextRail,EmptyState,Icon,PageHeading,TopicBar,dateLabel,streams} from '@/components/ui';
import {InformationRow} from '@/components/information-row';
import type {CatalogPage} from '@/lib/catalog';
import type {Plan,Profile} from '@/lib/api';

type Event={item_id:string;title:string;label:string;at:string;publication_id:string};

export default async function Home(){
  const [catalog,profile,plans,events,coverage] = await Promise.all([
    optionalWorkspaceApi('/v1/data/catalog?limit=4&status=active') as Promise<CatalogPage|null>,
    optionalWorkspaceApi('/v1/profile') as Promise<Profile|null>,
    optionalWorkspaceApi('/v1/plans') as Promise<Plan[]|null>,
    optionalWorkspaceApi('/v1/data/timeline') as Promise<Event[]|null>,
    Promise.all(streams.map(s => optionalWorkspaceApi('/v1/data/catalog?limit=1&status=active&path=' + s.code) as Promise<CatalogPage|null>)),
  ]);
  const pending = (plans || []).filter(p => p.status !== 'done');
  const upcoming = (events || []).filter(e => new Date(e.at).getTime() > Date.now()).sort((a,b) => new Date(a.at).getTime() - new Date(b.at).getTime());
  const target = streams.find(s => s.code === profile?.target_path);
  const agentEnabled = process.env.ENABLE_AGENT_UI === 'true';
  return <div className="shell home-shell">
    <PageHeading eyebrow="我的校园工作台" title={profile ? `你好，${profile.display_name || '同学'}。` : '欢迎来到校伴。'} description="找到值得关注的信息，把准备落实到每一步。">
      <Link className="button secondary" href="/data"><Icon name="search" size={16}/>发现信息</Link>
      {agentEnabled && <Link className="button primary" href="/agent"><Icon name="spark" size={16}/>问问校伴</Link>}
    </PageHeading>
    <div className="workspace-columns"><div>
      <section className="next-step-panel" aria-label="我的下一步">
        <div className="next-step-copy"><span className="next-step-kicker"><Icon name="check" size={16}/>从这里继续</span>
          <h2>{pending.length ? `还有 ${pending.length} 项准备，等你推进` : target ? `把${target.name}目标，拆成第一步` : '先选一个方向，再安排第一步'}</h2>
          <p>{pending.length ? pending[0].title : target ? '查看相关事项和原文，再为自己安排一个具体的准备任务。' : '不必一次决定未来。了解感兴趣的方向，从一件小事开始。'}</p>
          <div className="button-row"><Link className="button primary" href={pending.length ? '/tracker' : target ? '/data?path=' + target.code : '/paths'}>{pending.length ? '继续我的计划' : target ? '查看目标方向' : '了解发展路径'}<Icon name="arrow" size={16}/></Link><Link className="next-step-secondary" href={profile ? '/profile' : '/login'}>{target ? '调整发展目标' : '设置我的目标'}</Link></div>
        </div><div className="next-step-symbol" aria-hidden="true"><span/><span/><span/><Icon name="arrow" size={32}/></div>
      </section>
      <div className="overview-strip">
        <Link href="/data"><Icon name="file" size={17}/><span><strong>{catalog?.total ?? '—'}</strong> 项当前展示信息</span><Icon name="chevron" size={13}/></Link>
        <Link href="/tracker"><Icon name="check" size={17}/><span><strong>{plans ? pending.length : '—'}</strong> 项未完成计划</span><Icon name="chevron" size={13}/></Link>
        <Link href="/data/timeline"><Icon name="calendar" size={17}/><span><strong>{events ? upcoming.length : '—'}</strong> 个未来日程</span><Icon name="chevron" size={13}/></Link>
      </div>
      <section className="topic-section priority-section"><TopicBar title="接下来要留意的日程"><Link href="/data/timeline">完整时间线<Icon name="arrow" size={13}/></Link></TopicBar>
        {upcoming.length ? <div className="upcoming-list">{upcoming.slice(0,3).map((e,i) => <Link className="upcoming-item" key={e.item_id+e.label+i} href={'/data/'+e.publication_id}><time dateTime={e.at}>{dateLabel(e.at)}</time><span><small>{e.label}</small><strong>{e.title}</strong></span><Icon name="chevron" size={15}/></Link>)}</div> : <EmptyState icon="calendar" title={events ? '暂未收录后续日程' : '日程暂时未加载'} description="仅展示原文中已提取的日期。你也可以为自己的准备任务设置时间。" href="/tracker" label="管理个人计划"/>}
      </section>
      <section aria-label="探索发展方向" className="home-directions"><div className="section-title"><h2>你想往哪个方向走？</h2><Link href="/paths">路径指南<Icon name="arrow" size={13}/></Link></div>
        <div className="stream-grid">{streams.map((s,i) => <Link className={`stream-card ${target?.code === s.code ? 'is-target' : ''}`} key={s.code} href={'/data?path='+s.code}><span className="direction-icon"><Icon name={i === 0 ? 'book' : i === 1 ? 'file' : i === 2 ? 'link' : i === 3 ? 'shield' : i === 4 ? 'users' : 'spark'} size={20}/></span><div><strong>{s.name}{target?.code === s.code && <em>我的目标</em>}</strong><small>{s.note}</small><span className="direction-count">{coverage[i] ? coverage[i]!.total ? `${coverage[i]!.total} 条当前信息` : '暂未收录当前信息' : '信息暂未加载'}</span></div><Icon name="chevron" size={14}/></Link>)}</div>
      </section>
      <section className="topic-section"><TopicBar title="最近收录的信息"><Link href="/data">浏览全部<Icon name="arrow" size={13}/></Link></TopicBar>
        {catalog?.items.map(item => <InformationRow key={item.id} item={item}/>)}
        {!catalog ? <EmptyState title="信息暂时未加载" description="请前往信息中心重试。" href="/data" label="打开信息中心"/> : !catalog.items.length && <EmptyState title="暂未收录当前信息" description="当前列表不代表全部机会，报名信息请以官方渠道为准。" href="/paths" label="了解发展路径"/>}
      </section>
    </div><ContextRail>
      <section className="personal-progress"><div className="section-title"><h2>我的准备</h2><Link href="/tracker" aria-label="管理我的计划"><Icon name="arrow" size={15}/></Link></div>
        {pending.length ? pending.slice(0,4).map(p => <Link className="preparation-item" key={p.id} href="/tracker"><span className={`preparation-dot ${p.status === 'doing' ? 'in-progress' : ''}`}/><div><strong>{p.title}</strong><small>{p.status === 'doing' ? '进行中' : '待开始'}{p.due_date ? ' · ' + dateLabel(p.due_date) : ''}</small></div></Link>) : <><p>{plans ? '你的第一项计划，从这里开始。' : '登录后可保存个人准备计划。'}</p><Link className="button secondary" href={plans ? '/tracker' : '/login'}><Icon name="plus" size={14}/>{plans ? '创建一项计划' : '登录校伴'}</Link></>}
      </section>
      {agentEnabled && <section className="rail-tip assistant-tip"><span className="assistant-mark"><Icon name="spark" size={22}/></span><h3>想清楚，也做得到</h3><p>让校伴帮你比较方向、查找原文，再一起安排准备计划。</p><Link className="section-link" href="/agent">开始一次对话<Icon name="arrow" size={14}/></Link></section>}
      <section className="quick-tools"><h2>准备时会用到</h2><Link className="context-link" href="/eligibility"><span className="row"><Icon name="shield" size={16}/>核对报名条件</span><Icon name="chevron" size={13}/></Link><Link className="context-link" href="/knowledge"><span className="row"><Icon name="book" size={16}/>查找政策原文</span><Icon name="chevron" size={13}/></Link><Link className="context-link" href="/team-manager"><span className="row"><Icon name="users" size={16}/>寻找协作伙伴</span><Icon name="chevron" size={13}/></Link></section>
      <section className="source-note"><Icon name="shield" size={17}/><p>信息覆盖仍在完善。未收录不代表没有机会；具体条件与时间，请核对官方原文。</p></section>
    </ContextRail></div>
  </div>;
}

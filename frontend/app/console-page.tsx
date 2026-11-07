import Link from 'next/link';
import {optionalWorkspaceApi} from '@/lib/workspace';
import {HugeIcon,Icon,PageHeading,streams,type HugeIconName} from '@/components/ui';
import type {CatalogPage} from '@/lib/catalog';
import type {Plan,Profile} from '@/lib/api';
import {AnimatedCount} from '@/components/workspace-motion';
import {channelHref} from '@/lib/development-channels';

type Event={item_id:string;title:string;label:string;at:string;publication_id?:string};

const directionIcons: HugeIconName[] = ['book','analytics','compass','shield','briefcase','idea'];

function streamHref(code:string){
  return channelHref(code);
}

function dateKey(value:string){
  const date = new Date(value);
  if(Number.isNaN(date.getTime())) return '';
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2,'0');
  const day = String(date.getDate()).padStart(2,'0');
  return `${year}-${month}-${day}`;
}

export default async function Home(){
  const [catalog,profile,plans,events,coverage] = await Promise.all([
    optionalWorkspaceApi('/v1/data/catalog?limit=4&status=active') as Promise<CatalogPage|null>,
    optionalWorkspaceApi('/v1/profile') as Promise<Profile|null>,
    optionalWorkspaceApi('/v1/plans') as Promise<Plan[]|null>,
    optionalWorkspaceApi('/v1/data/timeline') as Promise<Event[]|null>,
    Promise.all(streams.map(s => optionalWorkspaceApi('/v1/data/catalog?limit=1&status=active&path=' + s.code) as Promise<CatalogPage|null>)),
  ]);

  const pending = (plans || []).filter(p => p.status !== 'done');
  const planEvents=(plans||[]).filter(plan=>plan.status!=='done'&&plan.due_date).map(plan=>({item_id:`plan-${plan.id}`,title:plan.title,label:'我的计划',at:plan.due_date!,publication_id:undefined}));
  const combinedEvents=[...(events||[]).filter(event=>!planEvents.some(plan=>plan.title===event.title&&dateKey(plan.at)===dateKey(event.at))),...planEvents];
  const upcoming = combinedEvents
    .filter(e => new Date(e.at).getTime() > Date.now())
    .sort((a,b) => new Date(a.at).getTime() - new Date(b.at).getTime());
  const target = streams.find(s => s.code === profile?.target_path);
  const agentEnabled = process.env.ENABLE_AGENT_UI === 'true';
  const continueHref = pending.length ? '/tracker' : target ? streamHref(target.code) : '/paths';
  const continueHint = pending.length
    ? `下一项：${pending[0].title}`
    : target
      ? `当前目标：${target.name}`
      : '选择一个方向，开始规划你的下一步';

  return <div className="shell console-page">
    <PageHeading eyebrow="我的校园工作台" title={`你好，${profile?.display_name || '同学'}`} description={continueHint}>
      <Link className="button primary console-continue" href={continueHref}>从这里继续<Icon name="arrow" size={16}/></Link>
    </PageHeading>

    <nav className="console-quick-actions" aria-label="快速操作">
      <Link data-motion-enter className="console-action-card" href="/paths">
        <span className="console-action-icon"><HugeIcon name="compass" size={23}/></span>
        <span><strong>了解发展路径</strong><small>看看六个方向，从兴趣开始</small></span>
        <Icon name="arrow" size={16}/>
      </Link>
      <Link data-motion-enter className="console-action-card" href="/settings">
        <span className="console-action-icon"><HugeIcon name="settings" size={23}/></span>
        <span><strong>设置我的目标</strong><small>完善画像，获得更合适的建议</small></span>
        <Icon name="arrow" size={16}/>
      </Link>
      <Link data-motion-enter className="console-action-card" href="/tracker">
        <span className="console-action-icon"><HugeIcon name="checklist" size={23}/></span>
        <span><strong>创建计划</strong><small>把想做的事拆成下一步</small></span>
        <Icon name="arrow" size={16}/>
      </Link>
      <Link data-motion-enter className="console-action-card" href={agentEnabled ? '/agent' : '/login'}>
        <span className="console-action-icon"><HugeIcon name="sparkles" size={23}/></span>
        <span><strong>和 AI 对话</strong><small>{agentEnabled ? '一起梳理方向与行动' : '登录后开启校伴对话'}</small></span>
        <Icon name="arrow" size={16}/>
      </Link>
    </nav>

    <section className="console-info-section" aria-labelledby="console-info-title">
      <div data-motion-enter className="console-section-heading">
        <div><p className="eyebrow">OVERVIEW</p><h2 id="console-info-title">当前信息</h2></div>
        <Link href="/data">打开信息中心<Icon name="arrow" size={14}/></Link>
      </div>
      <div className="console-stats">
        <Link data-motion-enter className="console-stat" href="/data"><span className="console-stat-icon"><HugeIcon name="file" size={20}/></span><span><strong><AnimatedCount value={catalog?.total ?? null}/></strong><small>项当前展示信息</small></span><Icon name="chevron" size={15}/></Link>
        <Link data-motion-enter className="console-stat" href="/tracker"><span className="console-stat-icon"><HugeIcon name="checklist" size={20}/></span><span><strong><AnimatedCount value={plans ? pending.length : null}/></strong><small>项未完成计划</small></span><Icon name="chevron" size={15}/></Link>
        <Link data-motion-enter className="console-stat" href="/data/timeline"><span className="console-stat-icon"><HugeIcon name="calendar" size={20}/></span><span><strong><AnimatedCount value={events ? upcoming.length : null}/></strong><small>个未来日程</small></span><Icon name="chevron" size={15}/></Link>
      </div>
    </section>

    <section className="console-directions" aria-labelledby="console-directions-title">
      <div data-motion-enter className="console-section-heading"><div><p className="eyebrow">EXPLORE YOUR NEXT CHAPTER</p><h2 id="console-directions-title">你想往哪个方向走？</h2></div><Link href="/paths">路径指南<Icon name="arrow" size={14}/></Link></div>
      <div className="console-direction-grid">{streams.map((stream,index)=><Link data-motion-enter className={`console-direction-card ${target?.code === stream.code ? 'is-target' : ''}`} key={stream.code} href={streamHref(stream.code)}>
        <span className="console-direction-icon"><HugeIcon name={directionIcons[index]} size={23}/></span>
        <span className="console-direction-copy"><strong>{stream.name}{target?.code === stream.code && <em>我的目标</em>}</strong><small>{stream.note}</small><span>{coverage[index] ? coverage[index]!.total ? `${coverage[index]!.total} 条当前信息` : '暂未收录当前信息' : '信息暂未加载'}</span></span>
        <Icon name="arrow" size={16}/>
      </Link>)}</div>
    </section>

    <nav data-motion-enter className="console-bottom-actions" aria-label="更多入口">
      <Link href="/teams"><span className="console-bottom-icon"><HugeIcon name="users" size={21}/></span><span><strong>找队友</strong><small>找到一起成长的人</small></span><Icon name="arrow" size={15}/></Link>
      <Link href={agentEnabled ? '/agent' : '/login'}><span className="console-bottom-icon"><HugeIcon name="sparkles" size={21}/></span><span><strong>问问校伴</strong><small>{agentEnabled ? '把问题交给 AI 一起想' : '登录后与校伴交流'}</small></span><Icon name="arrow" size={15}/></Link>
      <Link href="/data"><span className="console-bottom-icon"><HugeIcon name="file" size={21}/></span><span><strong>信息中心</strong><small>查看官方信息与原文</small></span><Icon name="arrow" size={15}/></Link>
    </nav>
  </div>;
}

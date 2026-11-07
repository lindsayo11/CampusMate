'use client';
import Link from 'next/link';
import {useEffect,useRef,useState} from 'react';
import type {Eligibility,Profile} from '@/lib/api';
import {archiveDate,evidenceRequest,externalUrl,sourceTypes,WorkspaceRequestError,type EligibilityOptions} from '@/lib/evidence-workspace';
import {Icon} from './ui';
import s from './evidence-workspace.module.css';

const profileFields=[['school','学校'],['degree','学历'],['grade','年级'],['major','专业'],['target_year','目标年份'],['language_score','语言成绩']] as const;
export function EligibilityPanel({initialId}:{initialId?:string}){
  const [options,setOptions]=useState<EligibilityOptions|null>(null),[profile,setProfile]=useState<Profile|null>(null);
  const [loading,setLoading]=useState(true),[loadError,setLoadError]=useState<WorkspaceRequestError|null>(null),[profileError,setProfileError]=useState(''),[retry,setRetry]=useState(0);
  const [selected,setSelected]=useState(''),[query,setQuery]=useState(''),[kind,setKind]=useState(''),[onlyRules,setOnlyRules]=useState(false),[shown,setShown]=useState(8);
  const [result,setResult]=useState<Eligibility|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState<WorkspaceRequestError|null>(null);
  const controller=useRef<AbortController|null>(null);
  useEffect(()=>{
    const abort=new AbortController();setLoading(true);setLoadError(null);setProfileError('');
    const list=evidenceRequest<EligibilityOptions>('/v1/eligibility/options',{signal:abort.signal}).then(data=>{
      setOptions(data);setSelected(previous=>data.items.some(x=>x.id===previous)?previous:data.items.some(x=>x.id===initialId)?initialId!:data.items.find(x=>x.rule_count>0)?.id||data.items.find(x=>x.deadline&&new Date(x.deadline)>new Date())?.id||data.items[0]?.id||'');
    }).catch(error=>{if(!abort.signal.aborted)setLoadError(error);});
    const personal=evidenceRequest<Profile>('/v1/profile',{signal:abort.signal}).then(setProfile).catch(error=>{if(!abort.signal.aborted){setProfile(null);setProfileError(error.message||'个人资料暂未加载');}});
    void Promise.all([list,personal]).finally(()=>{if(!abort.signal.aborted)setLoading(false);});
    return ()=>abort.abort();
  },[initialId,retry]);
  useEffect(()=>()=>controller.current?.abort(),[]);
  function choose(id:string){controller.current?.abort();setBusy(false);setSelected(id);setResult(null);setError(null);}
  async function check(){
    if(!selected||busy)return;controller.current?.abort();const abort=new AbortController();controller.current=abort;
    setBusy(true);setError(null);setResult(null);
    try{setResult(await evidenceRequest<Eligibility>('/v1/tools/eligibility_check',{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({opportunity_id:selected})}));}
    catch(error){if(!abort.signal.aborted)setError(error as WorkspaceRequestError);}
    finally{if(!abort.signal.aborted)setBusy(false);}
  }
  const chosen=options?.items.find(x=>x.id===selected);
  const filtered=(options?.items||[]).filter(x=>(!kind||x.type===kind)&&(!onlyRules||x.rule_count>0)&&(!query.trim()||[x.title,x.organization,x.summary].join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())));
  const filled=profile?profileFields.filter(([key])=>String(profile[key]??'').trim()).length:0;
  const missing=chosen?.rules.filter(rule=>!String(profile?.[rule.field as keyof Profile]??'').trim()).map(rule=>rule.label)||[];
  return <div className={s.page}>
    <header className={s.heading}><div><span className={s.titleIcon}><Icon name="shield" size={23}/></span><div><h1>资格核对</h1><p>选定一件事，看看条件与自己是否对应。</p></div></div><Link href="/knowledge">查找原文依据<Icon name="arrow" size={16}/></Link></header>
    <section className={s.profileStrip} aria-label="核对使用的个人资料"><div className={s.profileTitle}><Icon name="users" size={20}/><div><h2>我的核对资料</h2><span>{profile?'基本资料 '+filled+' / '+profileFields.length+' 项已填写':profileError?'个人资料未加载':'正在读取个人资料'}</span></div></div>
      {profile?<dl>{profileFields.slice(0,4).map(([key,label])=><div key={key}><dt>{label}</dt><dd>{String(profile[key]||'未填写')}</dd></div>)}</dl>:<p role={profileError?'alert':'status'}>{profileError||'加载中…'}{profileError&&<button onClick={()=>setRetry(retry+1)}>重试</button>}</p>}
      <Link href="/settings">编辑资料<Icon name="arrow" size={14}/></Link>
    </section>
    <div className={s.checkLayout}>
      <aside className={s.choices} aria-label="核对事项列表"><div className={s.sectionTitle}><div><h2>选择事项</h2><span>{options?options.total+' 项公开机会':'加载中…'}</span></div></div>
        <label className={s.searchInput}><Icon name="search" size={17}/><input aria-label="搜索核对事项" placeholder="搜索事项、院校…" value={query} onChange={e=>{setQuery(e.target.value);setShown(8);}}/></label>
        <div className={s.choiceFilters}><select aria-label="核对事项板块" value={kind} onChange={e=>{setKind(e.target.value);setShown(8);}}><option value="">全部板块</option>{[...new Set(options?.items.map(x=>x.type)||[])].map(type=><option key={type} value={type}>{sourceTypes[type]||type}</option>)}</select><label><input type="checkbox" checked={onlyRules} onChange={e=>{setOnlyRules(e.target.checked);setShown(8);}}/>有核验条件</label></div>
        {loadError&&<div className={s.notice} role="alert"><p>{loadError.message}</p>{loadError.status===401||loadError.status===403?<Link href="/login">去登录</Link>:<button onClick={()=>setRetry(retry+1)}>重试</button>}</div>}
        {loading&&!options&&<div className={s.loading} role="status">正在加载事项…</div>}
        <div className={s.choiceList}>{filtered.slice(0,shown).map(item=><button className={s.choice} key={item.id} type="button" aria-pressed={selected===item.id} onClick={()=>choose(item.id)}><small>{sourceTypes[item.type]||'公开事项'}</small><strong>{item.title}</strong><span>{item.rule_count?item.rule_count+' 项已核验条件':'条件待补充'}<Icon name="chevron" size={14}/></span></button>)}</div>
        {!loading&&!loadError&&!filtered.length&&<div className={s.empty}><h3>{onlyRules?'暂没有已核验条件的事项':'没有找到对应事项'}</h3><p>已收录公告不代表资格条件已齐全。</p><button onClick={()=>{setOnlyRules(false);setKind('');setQuery('');}}>查看全部事项</button></div>}
        {filtered.length>shown&&<button className={s.showMore} type="button" onClick={()=>setShown(shown+8)}>再看 {Math.min(8,filtered.length-shown)} 项<Icon name="plus" size={14}/></button>}
      </aside>
      <section className={s.checkMain} aria-label="当前事项核对">
        {!chosen?<div className={s.empty}><Icon name="shield" size={32}/><h2>从一件具体的事开始</h2><p>选择公告后，可查看来源、时间和已核验条件。</p><Link href="/knowledge">浏览已收录原文</Link></div>:<>
          <header className={s.selectedHeading}><div className={s.cardMeta}><span>{sourceTypes[chosen.type]||'公开事项'}</span><span>{chosen.rule_count?chosen.rule_count+' 项可核对条件':'待补充资格条件'}</span></div><h2>{chosen.title}</h2><p>{chosen.summary}</p>
            <dl className={s.selectedFacts}><div><dt>发布 / 来源</dt><dd>{chosen.source_label||chosen.organization}</dd></div><div><dt>截止日期</dt><dd>{archiveDate(chosen.deadline)}</dd></div><div><dt>地点 / 范围</dt><dd>{chosen.location||'请核对原文'}</dd></div></dl>
            <div className={s.selectedActions}><button className={s.primary} disabled={busy||!profile} onClick={()=>void check()}>{busy?'正在核对…':'开始核对'}<Icon name="arrow" size={15}/></button>{externalUrl(chosen.source_url)&&<a href={externalUrl(chosen.source_url)} target="_blank" rel="noreferrer">查看官方原文<Icon name="link" size={15}/></a>}<Link href={'/opportunity/'+encodeURIComponent(chosen.id)}>查看事项</Link></div>
          </header>
          {error&&<div className={s.notice} role="alert"><span>{error.message}</span>{error.status===401||error.status===403?<Link href="/login">重新登录</Link>:<button onClick={()=>void check()}>重新核对</button>}</div>}
          {busy&&<p className={s.loading} role="status">正在对照个人资料与已核验条件…</p>}
          {result?<div className={s.result} role="status"><div className={s.resultTitle}><Icon name={result.eligible===true?'check':'shield'} size={23}/><div><small>本次核对</small><h3>{result.results.length===0?'缺少条件资料，暂不能判断':result.eligible===true?'已录入条件通过':result.eligible===false?'有不符合的已录入条件':'部分资料不足，需要补充'}</h3></div></div>
            {result.results.length===0?<p>请对照官方公告及附件。部分官网受到反爬、登录或附件限制，可下载 PDF、Word 或 Excel 后交由管理员导入核验。</p>:<><div className={s.ruleResults}>{result.results.map((rule,i)=><article key={i}><div><strong>{rule.label}</strong><span className={rule.passed===false?s.failed:s.ruleStatus}>{rule.passed===null?'待补充':rule.passed?'通过':'不符合'}</span></div><dl><div><dt>我的资料</dt><dd>{rule.actual||'未填写'}</dd></div><div><dt>原文要求</dt><dd>{rule.expected||'未注明'}</dd></div></dl>{rule.evidence&&<blockquote>{rule.evidence}</blockquote>}{externalUrl(rule.source_url)&&<a href={externalUrl(rule.source_url)} target="_blank" rel="noreferrer">查看条件来源<Icon name="link" size={14}/></a>}</article>)}</div><p className={s.quiet}>仅核对已录入条件，不代表全部报名要求已满足。</p></>}
            <div className={s.selectedActions}><Link href="/settings">补充个人资料<Icon name="arrow" size={14}/></Link><Link href="/knowledge">查找原文依据<Icon name="book" size={14}/></Link></div>
          </div>:<section className={s.preflight}><div className={s.sectionTitle}><h3>核对前，先看这里</h3><span>{chosen.rule_count} 项已核验条件</span></div>
            {chosen.rules.length>0?<ul className={s.requirementList}>{chosen.rules.map((rule,i)=><li key={i}><Icon name="check" size={17}/><div><strong>{rule.label}</strong><p>{rule.expected}{!rule.supported&&' · 需要人工核对'}</p></div></li>)}</ul>:<p className={s.quiet}>已收录公告内容，资格条件尚未补齐。你可以先阅读原文，准备这些核对材料。</p>}
            {missing.length>0&&<p className={s.notice}>以下条件对应的个人资料未填写：{missing.join('、')}</p>}
            <ol className={s.preparation}><li><span>01</span><div><strong>确认报名对象</strong><p>学历、学籍、专业或地区限制，以本次公告为准。</p></div></li><li><span>02</span><div><strong>备好官方附件</strong><p>查看岗位表、招生目录、竞赛章程和补充通知。</p></div></li><li><span>03</span><div><strong>核对时间与材料</strong><p>确认截止时间及提交方式，再安排个人计划。</p></div></li></ol><small className={s.quiet}>以上是核对步骤，不是该公告新增的报名条件。</small>
          </section>}
        </>}
      </section>
    </div>
    <aside className={s.bottomNote}><Icon name="file" size={18}/><p>有原文、附件和对应个人资料，才能做有依据的核对。</p><Link href="/data/timeline">查看发展日历<Icon name="arrow" size={14}/></Link></aside>
  </div>;
}

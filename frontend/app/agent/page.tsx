"use client";
import {useEffect,useRef,useState,type FormEvent,type ReactNode} from 'react';
import Link from 'next/link';
import {apiBase} from '@/lib/api';
import type {CatalogItem} from '@/lib/catalog';
import {safeSourceUrl,availabilityLabels} from '@/lib/explore';
import {MarkdownDraft} from '@/components/markdown-draft';
import {Icon,dateLabel} from '@/components/ui';
import {NeedsQuestionnaire,type AssessmentAnswers} from '@/components/needs-questionnaire';
import styles from '@/components/assistant-studio.module.css';

type Result=Record<string,unknown>;
type Reply={status:string;message?:string;conversation_id?:string;action_id?:string;expires_at?:string;tool?:string;arguments?:{plans?:{title:string;note:string;steps?:string[]}[];markdown?:string;project_revision?:number;notice?:string;title?:string;status?:string;due_at?:string};result?:Result};
type Turn={query:string;reply:Reply};
type Item={id:string|number;title:string;publication_id?:string;status?:string;deadline?:string;due_date?:string};
type AssessmentResult={assessment:AssessmentAnswers;focus:string;rationale:string[];tasks:{title:string;steps:string[]}[];matches:CatalogItem[];reference_only:boolean;notice:string};
const choices=[['auto','自由对话'],['chat','对话'],['paths','路径咨询'],['profile','我的画像'],['search','信息查询'],['eligibility','资格核对'],['plan','准备计划'],['tasks','我的任务'],['review','进度复盘'],['startup','创业咨询'],['startup_document','创业文稿'],['update_task','更新任务'],['reminder','创建提醒'],['knowledge','原文检索'],['materials','材料建议'],['assessment','需求方案']];
async function api(url:string,method='GET',body?:unknown){
 const response=await fetch(apiBase+url,{method,headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});
 const data=await response.json().catch(()=>null);
 if(!response.ok)throw Error(response.status===401?'请登录后继续对话。':typeof data?.detail==='string'?data.detail:'暂时无法处理，请稍后重试。');
 return data;
}
function AssistantBubble({children}:{children:ReactNode}){return <div className={styles.message}><span className={styles.avatar}><img src="/landing/assets/logo.svg" alt="校伴头像"/></span><div><span className={styles.messageName}>校伴</span><div className={styles.bubble}>{children}</div></div></div>}
function ResultSummary({data}:{data:Result}){
 const paths=(data.paths||[]) as {id:number;name:string}[],refs=(data.references||[]) as {url:string;quote:string;location:string}[],web=(data.web_sources||[]) as {title:string;url:string;snippet?:string;published_date?:string|null;official?:boolean}[],rules=(data.results||[]) as {label:string;actual:string;expected:string;passed:boolean|null}[],saved=(data.plans||[]) as {id:number;title:string}[];
 const summary=data.summary as {total:number;todo:number;doing:number;done:number;overdue:number;completion_percent:number;steps_total:number;steps_done:number}|undefined;
 return <>{typeof data.workspace_url==='string'&&<Link className="button secondary" href={data.workspace_url}>打开创业工作台 →</Link>}{Array.isArray(data.startup_projects)&&<div className="agent-result-card"><h4>我的创业项目</h4>{(data.startup_projects as {id:string;name:string}[]).map(p=><p key={p.id}><Link href={'/startup?project='+p.id}>{p.name}</Link></p>)}</div>}{data.startup_document&&typeof data.startup_document==='object'?<p>创业文稿已保存为 v{String((data.startup_document as {version:number}).version)}，可在工作台继续编辑和下载。</p>:null}{typeof data.model_notice==='string'&&<p className="field-hint" role="status">{data.model_notice}</p>}{summary&&<div className="agent-result-card"><h4>个人执行进度 · {summary.completion_percent}%</h4><p>共 {summary.total} 项 · 待开始 {summary.todo} · 进行中 {summary.doing} · 已完成 {summary.done}</p><p>逾期 {summary.overdue} 项 · 准备清单 {summary.steps_done}/{summary.steps_total}</p><Link href="/tracker">管理计划与清单 →</Link></div>}{typeof data.model_explanation==='string'&&<p className="agent-grounded-answer" style={{whiteSpace:'pre-wrap'}}>{data.model_explanation}</p>}{web.length>0&&<div className="agent-result-card agent-web-sources"><h4>联网来源</h4>{web.map((source,i)=><p className="agent-web-source" key={source.url}><span className="badge">[{i+1}] {source.official?'官方来源':'公开网页'}</span> <a href={safeSourceUrl(source.url)} target="_blank" rel="noreferrer">{source.title}</a>{source.published_date&&<small className="muted"> · {source.published_date}</small>}{source.snippet&&<><br/><small>{source.snippet}</small></>}</p>)}</div>}{paths.length>0&&<div className="tagrow">{paths.map(p=><span key={p.id}>{p.name}</span>)}</div>}{Array.isArray(data.suggestions)&&<ul>{(data.suggestions as string[]).map((s,i)=><li key={i}>{s}</li>)}</ul>}{'eligible' in data&&<p className="badge">条件核对：{data.eligible===true?'已核对的规则符合':data.eligible===false?'存在不符合的规则':'信息不足，不能确定'}</p>}{rules.map((r,i)=><div className="agent-result-card" key={i}><h4>{r.label} · {r.passed===true?'符合':r.passed===false?'不符合':'待补充或核验'}</h4><p>当前：{r.actual||'未填写'} · 要求：{r.expected}</p></div>)}{refs.map((r,i)=><blockquote key={i}>{r.quote}<p><a href={safeSourceUrl(r.url)} target="_blank" rel="noreferrer">核对原文</a> · {r.location}</p></blockquote>)}{saved.length>0&&<div className="agent-result-card"><h4>已保存 {saved.length} 项计划</h4>{saved.map(p=><p key={p.id}>✓ {p.title}</p>)}<Link href="/tracker">去我的计划查看 →</Link></div>}{typeof data.display_name==='string'&&<div className="agent-result-card"><h4>{data.display_name}的个人画像</h4><p>{String(data.school||'学校待填写')} · {String(data.major||'专业待填写')} · {String(data.grade||'年级待填写')}</p><p>目标：{String(data.target_path||'尚未确定')}</p><Link href="/profile">完善个人资料 →</Link></div>}{typeof data.reminder_id==='string'&&<Link className="button secondary" href="/notifications">查看已保存的提醒</Link>}{typeof data.source==='string'&&<p className="muted">依据：{data.source}</p>}{typeof data.message==='string'&&<p>{data.message}</p>}</>;
}

export default function Agent(){
 const [query,setQuery]=useState(''),[intent,setIntent]=useState('auto'),[cid,setCid]=useState<string>(),[turns,setTurns]=useState<Turn[]>([]),[sessions,setSessions]=useState<{id:string;title:string}[]>([]);
 const [context,setContext]=useState<Record<string,string>>({}),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState(''),[collapsed,setCollapsed]=useState(true),[more,setMore]=useState(false);
 const [questionnaire,setQuestionnaire]=useState(true),[initial,setInitial]=useState<AssessmentAnswers>(),[questionKey,setQuestionKey]=useState(0),[due,setDue]=useState(''),[planStatus,setPlanStatus]=useState('doing'),[historyError,setHistoryError]=useState('');
 const input=useRef<HTMLTextAreaElement>(null),bottom=useRef<HTMLDivElement>(null),historyPanel=useRef<HTMLElement>(null),historyToggle=useRef<HTMLButtonElement>(null);
 useEffect(()=>{
  if(collapsed)return;
  const outside=(event:Event)=>{if(event.target instanceof Node&&!historyPanel.current?.contains(event.target)&&!historyToggle.current?.contains(event.target))setCollapsed(true)};
  const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();setCollapsed(true);historyToggle.current?.focus()}};
  document.addEventListener('pointerdown',outside);document.addEventListener('focusin',outside);document.addEventListener('keydown',escape);
  return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('focusin',outside);document.removeEventListener('keydown',escape)};
 },[collapsed]);
 async function refresh(){const rows=await api('/v1/development-agent/conversations');setSessions(rows);setMore(rows.length===30);setHistoryError('')}
 async function retryHistory(){setLoading(true);setHistoryError('');try{await refresh()}catch(e){setHistoryError((e as Error).message)}finally{setLoading(false)}}
 useEffect(()=>{let alive=true;const params=new URLSearchParams(window.location.search),requested=params.get('intent')||'auto';
  if(choices.some(([v])=>v===requested))setIntent(requested);
  const ctx:Record<string,string>={};for(const key of ['publication_id','item_id','plan_id','startup_project_id','keyword'])if(params.get(key))ctx[key]=params.get(key)!;
  if(params.get('path'))ctx.path_code=params.get('path')!;
  setContext(ctx);
  const prompt=params.get('prompt')||({eligibility:'请核对我是否符合这个事项的申请条件',plan:'请为我制定这个方向的准备计划',reminder:'为这项计划设置提醒',startup:'围绕这个项目给我创业建议'} as Record<string,string>)[requested]||'';
  setQuery(prompt);if(requested!=='auto'||prompt)setQuestionnaire(false);
  api('/v1/development-agent/conversations').then(rows=>{if(alive){setSessions(rows);setMore(rows.length===30)}}).catch(e=>{if(alive)setHistoryError(e.message)}).finally(()=>{if(alive)setLoading(false)});
  return()=>{alive=false};
 },[]);
 function reset(){if(busy)return;setCollapsed(true);setCid(undefined);setTurns([]);setContext({});setQuery('');setIntent('auto');setError('');setQuestionnaire(true);setInitial(undefined);setQuestionKey(k=>k+1);setDue('')}
 function preset(next:string,text:string){setIntent(next);setQuery(text);setQuestionnaire(false);input.current?.focus()}
 async function submit(text:string,nextIntent:string,extra:Record<string,unknown>={}){
  if(busy||!text.trim())return;setBusy(true);setError('');
  try{const payload={query:text,intent:nextIntent,conversation_id:cid,...context,...(context.plan_id?{plan_id:Number(context.plan_id)}:{}),status:planStatus,...(due?{due_at:new Date(due).toISOString()}:{}),...extra};
    const reply=await api('/v1/development-agent/chat','POST',payload);
    setCid(reply.conversation_id);setTurns(t=>[...t,{query:text,reply}]);setQuery('');setQuestionnaire(false);setIntent('auto');
    await refresh().catch(()=>{});
    setTimeout(()=>bottom.current?.scrollIntoView({block:'nearest',behavior:'auto'}),0);
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 async function send(e:FormEvent){e.preventDefault();if(intent==='eligibility'&&(!context.publication_id||!context.item_id)){setError('先查找一条公告，再选择“核对资格”。');return}
  if(['reminder','update_task'].includes(intent)&&!context.plan_id){setError('请从你的个人计划选择一项任务。');return}
  if(intent==='reminder'&&!due){setError('请填写提醒时间。');return}await submit(query,intent);
 }
 async function choose(id:string){setBusy(true);setError('');setHistoryError('');try{setTurns(await api('/v1/development-agent/conversations/'+id));setCid(id);setQuestionnaire(false);setContext({});setQuery('');setIntent('auto');setDue('');setCollapsed(true);historyToggle.current?.focus()}catch(e){setHistoryError((e as Error).message)}finally{setBusy(false)}}
 async function action(index:number,operation:string){setBusy(true);setError('');try{const reply=await api('/v1/development-agent/actions/'+turns[index].reply.action_id+'/'+operation,'POST',{});setTurns(t=>t.map((x,i)=>i===index?{...x,reply:{...x.reply,...reply}}:x))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function loadMore(){setBusy(true);setHistoryError('');try{const rows=await api('/v1/development-agent/conversations?offset='+sessions.length);setSessions(s=>[...s,...rows]);setMore(rows.length===30)}catch(e){setHistoryError((e as Error).message)}finally{setBusy(false)}}
 const openQuestionnaire=(answers?:AssessmentAnswers)=>{setInitial(answers);setQuestionKey(k=>k+1);setQuestionnaire(true);setTimeout(()=>bottom.current?.scrollIntoView({block:'nearest',behavior:'auto'}),0)};
 return <div className={styles.studio}>
  <header className={styles.heading}><div><h1>校伴助手</h1><p>从了解你开始，一起找到下一步。</p></div><Link href="/tracker">我的计划<Icon name="arrow" size={15}/></Link></header>
  <div className={styles.workspace}>
   <section className={styles.main} aria-label="校伴对话">
    <div className={styles.conversationToolbar}>
     <div className={styles.historyControl}>
      <button type="button" ref={historyToggle} className={styles.collapse} data-collapsed={collapsed} onClick={()=>setCollapsed(v=>!v)} aria-expanded={!collapsed} aria-controls="assistant-session-history" aria-label={collapsed?'展开助手会话':'收起助手会话'} title={collapsed?'展开助手会话':'收起助手会话'}><Icon name="chevron" size={18}/></button>
      <aside ref={historyPanel} id="assistant-session-history" className={styles.rail} aria-label="助手会话" hidden={collapsed}>
       <h2>最近会话</h2>
       <div className={styles.sessionList} aria-busy={loading||busy}>
        {loading&&<p role="status">正在读取…</p>}
        {sessions.map(s=><button type="button" className={styles.session} key={s.id} title={s.title} aria-current={s.id===cid?'true':undefined} disabled={busy} onClick={()=>void choose(s.id)}><span>{s.title}</span></button>)}
        {historyError&&<div className={styles.historyError} role="alert"><p>{historyError}</p>{historyError.includes('登录')?<Link href="/login">重新登录 →</Link>:!sessions.length&&<button type="button" disabled={loading} onClick={()=>void retryHistory()}>重新读取</button>}</div>}
        {more&&<button type="button" className={styles.loadSessions} disabled={busy} onClick={()=>void loadMore()}>加载更多</button>}
        {!loading&&!historyError&&!sessions.length&&<p>从这里开始第一段对话。</p>}
       </div>
      </aside>
     </div>
     <span className={styles.conversationTitle}>{sessions.find(s=>s.id===cid)?.title||'校伴对话'}</span>
     <button type="button" className={styles.newConversation} disabled={busy} onClick={reset}><Icon name="plus" size={15}/>新会话</button>
    </div>
    <div className={styles.conversation}>
     {!turns.length&&<><AssistantBubble><p className={styles.hello}>你好，我是校伴。</p></AssistantBubble><AssistantBubble><p className={styles.intro}>一起找到适合你的机会，把下一步变成行动。</p><p className={styles.notice}>可以先回答 8 个小问题，也可以直接告诉我你的想法。</p><div className={styles.suggestions}><button onClick={()=>preset('search','保研有什么要求')}>保研有什么要求？</button><button onClick={()=>preset('search','大学生竞赛')}>看看竞赛信息</button><button onClick={()=>preset('review','复盘我的执行进度，下一步做什么')}>复盘我的计划</button></div></AssistantBubble></>}
     {turns.map((turn,index)=><div key={index}><div className={styles.message+' '+styles.user}><span className={styles.avatar}>我</span><div className={styles.bubble}><p>{turn.query}</p></div></div>
      <AssistantBubble>{turn.reply.message&&<p>{turn.reply.message}</p>}
       {turn.reply.tool==='assessment'&&turn.reply.result?(()=>{const result=turn.reply.result as unknown as AssessmentResult;return <div>
        <h3 className={styles.resultHeading}>{result.focus} · 你的起步方案</h3><ul className={styles.rationale}>{result.rationale.map((r,i)=><li key={i}>{r}</li>)}</ul>
        <ol className={styles.tasks}>{result.tasks.map((task,i)=><li key={i}><div><strong>{task.title}</strong>{task.steps.map((s,j)=><p key={j}>{s}</p>)}</div></li>)}</ol>
        <p className={styles.notice}>{result.notice}</p>
        <div className={styles.resultActions}><button className={styles.primary} disabled={busy} onClick={()=>void submit('根据这次问卷，为我生成准备计划预览','plan',{assessment:result.assessment})}>生成计划预览<Icon name="arrow" size={15}/></button><button disabled={busy} onClick={()=>openQuestionnaire(result.assessment)}>修改回答</button></div>
        <div className={styles.matches}><h4>{result.reference_only?'已收录参考信息':'与你的方向相关'} · {result.matches.length} 条</h4>{result.reference_only&&<p className={styles.notice}>暂未找到当前可申请事项，以下为已收录参考资料，请留意时间与适用条件。</p>}{result.matches.map(match=><Link key={match.id} href={'/data/'+match.publication_id+'?item='+encodeURIComponent(match.id)}>{match.title}<small>{match.source.name} · {availabilityLabels[match.availability||'']||'请核对原文'}</small></Link>)}{!result.matches.length&&<p className={styles.notice}>当前资料库暂未找到相关公告。可到信息中心调整关键词。</p>}<Link href="/data">继续浏览信息中心 →</Link></div>
       </div>})():null}
       {turn.reply.status==='confirmation_required'&&turn.reply.arguments&&<div className="agent-result-card"><p className={styles.notice}>计划尚未保存，请先检查。</p>{turn.reply.arguments.plans?.map((plan,i)=><div key={i}><h4>{i+1}. {plan.title}</h4><p style={{whiteSpace:'pre-wrap'}}>{plan.note}</p><ul>{plan.steps?.map((s,j)=><li key={j}>{s}</li>)}</ul></div>)}
        {turn.reply.arguments.markdown&&<details open><summary>文稿预览 · v{turn.reply.arguments.project_revision}</summary><MarkdownDraft text={turn.reply.arguments.markdown}/><p>{turn.reply.arguments.notice}</p></details>}
        {turn.reply.arguments.title&&<h4>{turn.reply.arguments.title}</h4>}{turn.reply.arguments.status&&<p>更新为：{({todo:'待开始',doing:'进行中',done:'已完成'} as Record<string,string>)[turn.reply.arguments.status]}</p>}{turn.reply.arguments.due_at&&<p>提醒时间：{new Date(turn.reply.arguments.due_at).toLocaleString('zh-CN')}</p>}
        <div className={styles.resultActions}><button className={styles.primary} disabled={busy} onClick={()=>void action(index,'confirm')}>确认保存</button><button disabled={busy} onClick={()=>void action(index,'cancel')}>取消</button></div><small className={styles.notice}>{turn.reply.expires_at?'有效至 '+new Date(turn.reply.expires_at).toLocaleTimeString('zh-CN'):'10 分钟内有效'}</small>
       </div>}
       {turn.reply.result&&turn.reply.tool!=='assessment'&&<>{((turn.reply.result.items as Item[]|undefined)||[]).map(item=><div className="agent-result-card" key={item.id}><h4>{item.title}</h4><p>{item.deadline?'截止 '+dateLabel(item.deadline):item.due_date?'个人安排 '+dateLabel(item.due_date):''}</p><div className={styles.resultActions}>{item.publication_id?<><Link href={'/data/'+item.publication_id+'?item='+item.id}>详情与来源 →</Link><button disabled={busy} onClick={()=>{setContext({publication_id:item.publication_id!,item_id:String(item.id)});preset('eligibility','请核对我是否符合这个事项的条件')}}>核对资格</button></>:<><Link href="/tracker">查看计划 →</Link><button disabled={busy} onClick={()=>{setContext({plan_id:String(item.id)});preset('reminder','为这项计划设置提醒')}}>设置提醒</button><button disabled={busy} onClick={()=>{setContext({plan_id:String(item.id)});preset('update_task','更新这项计划的进度')}}>更新进度</button></>}</div></div>)}
        {Array.isArray(turn.reply.result.items)&&!turn.reply.result.items.length&&!((turn.reply.result.web_sources as unknown[])||[]).length&&!((turn.reply.result.references as unknown[])||[]).length&&typeof turn.reply.result.model_explanation!=='string'&&<p className={styles.notice}>暂未找到匹配记录，可以换个关键词再试。</p>}
        <ResultSummary data={turn.reply.result}/></>}
       {turn.reply.status==='cancelled'&&<p>已取消，未保存。</p>}{turn.reply.status==='expired'&&<p>预览已过期，请重新生成。</p>}
      </AssistantBubble></div>)}
     {questionnaire&&<AssistantBubble><NeedsQuestionnaire key={questionKey} initial={initial} busy={busy||loading} onComplete={answers=>void submit('我已完成需求问卷，请帮我规划下一步。','assessment',{assessment:answers})} onCancel={()=>{setQuestionnaire(false);input.current?.focus()}}/></AssistantBubble>}
     {busy&&<p className={styles.pending} role="status">校伴正在整理，请稍候…</p>}<div ref={bottom}/>
    </div>
    <form className={styles.composer} onSubmit={send}>
     {intent!=='auto'&&<div className={styles.context}><span>{choices.find(([v])=>v===intent)?.[1]||intent}{context.item_id?' · 已选择公告':''}</span><button type="button" onClick={()=>{setIntent('auto');setContext({});setDue('')}}>清除</button>{intent==='reminder'&&<label>提醒时间<input type="datetime-local" aria-label="提醒时间" value={due} onChange={e=>setDue(e.target.value)} required/></label>}{intent==='update_task'&&<select aria-label="计划进度" value={planStatus} onChange={e=>setPlanStatus(e.target.value)}><option value="todo">待开始</option><option value="doing">进行中</option><option value="done">已完成</option></select>}</div>}
     <div className={styles.composeBox}><textarea ref={input} aria-label="给校伴的消息" value={query} onChange={e=>setQuery(e.target.value)} disabled={busy} maxLength={6000} placeholder="说说你的想法，或问我一条公告…" required onKeyDown={e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)&&!e.nativeEvent.isComposing){e.preventDefault();e.currentTarget.form?.requestSubmit()}}}/><div className={styles.composeTools}><button type="button" disabled={busy} onClick={()=>openQuestionnaire()}><Icon name="spark" size={14}/>需求小问卷</button><button className={styles.primary} disabled={busy||loading||!query.trim()}>发送<Icon name="send" size={15}/></button></div></div>
     {error&&<div className={styles.error} role="alert">{error}{error.includes('登录')&&<Link href="/login">重新登录 →</Link>}</div>}
    </form>
   </section>
  </div>
 </div>;
}

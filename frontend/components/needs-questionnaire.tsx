"use client";
import {useState} from 'react';
import {Icon} from './ui';
import styles from './assistant-studio.module.css';

export type AssessmentAnswers={stage:string;direction:string;subject:string;goal:string;hours:number;experience:string;collaboration:string;horizon:string};
const questions:{key:keyof AssessmentAnswers;group:string;title:string;options?:[string|number,string][]}[]=[
  {key:'stage',group:'学业背景',title:'你现在处于哪个阶段？',options:[['early','本科低年级'],['junior','本科三年级'],['senior','本科毕业年级'],['graduate','研究生'],['working','已毕业']]},
  {key:'direction',group:'发展方向',title:'这次想重点探索什么？',options:[['explore','还没确定'],['competition','竞赛实践'],['recommendation_exemption','保研推免'],['domestic_postgraduate_exam','国内考研'],['overseas_study','境外留学'],['national_civil_service','考公考编'],['employment','实习就业'],['entrepreneurship','创新创业']]},
  {key:'subject',group:'专业与兴趣',title:'你的专业或最想投入的领域是什么？'},
  {key:'goal',group:'本次目标',title:'你更希望获得什么？',options:[['research','为继续深造和科研做准备'],['career','找到实习或就业机会'],['skills','积累能力与作品'],['startup','验证一个创业想法'],['unsure','先比较方向，再做选择']]},
  {key:'hours',group:'时间投入',title:'每周可以留出多少小时？',options:[[4,'4 小时'],[8,'8 小时'],[12,'12 小时'],[20,'20 小时']]},
  {key:'experience',group:'已有准备',title:'哪种情况最接近你现在的经历？',options:[['starting','刚开始，想从基础准备起步'],['project','已经做过课程或实践项目'],['award','有竞赛或获奖经历'],['research','有科研训练或研究成果']]},
  {key:'collaboration',group:'协作方式',title:'你倾向怎样开展准备？',options:[['solo','先独立推进'],['team','希望找到队友'],['either','两种都可以']]},
  {key:'horizon',group:'准备周期',title:'这次方案先覆盖多长时间？',options:[['month','未来一个月'],['semester','这个学期'],['year','未来一年']]},
];
export function NeedsQuestionnaire({initial,onComplete,onCancel,busy}:{initial?:AssessmentAnswers;onComplete:(answers:AssessmentAnswers)=>void;onCancel:()=>void;busy:boolean}){
  const [answers,setAnswers]=useState<Partial<AssessmentAnswers>>(initial||{}),[step,setStep]=useState(0);
  const question=questions[step],value=answers[question.key],last=step===questions.length-1;
  const valid=question.key==='hours'?typeof value==='number'&&Number.isInteger(value)&&value>=2&&value<=40:typeof value==='string'&&value.trim().length>0;
  const update=(next:string|number)=>setAnswers(a=>({...a,[question.key]:next}));
  return <section className={styles.questionnaire} aria-label="需求问卷">
    <div className={styles.questionProgress}><b>问题 {step+1} / {questions.length} · {question.group}</b><span>{Math.round((step+1)/questions.length*100)}%</span></div>
    <progress max={questions.length} value={step+1} aria-label="问卷进度"/>
    <h3 id="question-title" aria-live="polite">{question.title}</h3>
    <div className={styles.options} role="group" aria-labelledby="question-title">
      {question.options?.map(([key,label])=><button type="button" disabled={busy} aria-pressed={value===key} key={key} onClick={()=>update(key)}><span className={styles.radio}/>{label}</button>)}
    </div>
    {question.key==='subject'&&<input autoFocus aria-label="专业或兴趣领域" value={answers.subject||''} onChange={e=>update(e.target.value)} maxLength={80} placeholder="例如：计算机科学、商科、医学、设计"/>}
    {question.key==='hours'&&<label className={styles.hours}>自定时间<input type="number" aria-label="每周投入小时数" min={2} max={40} step={1} value={answers.hours||''} onChange={e=>update(Number(e.target.value))}/>小时 / 周</label>}
    <div className={styles.questionFooter}><button type="button" onClick={()=>setStep(s=>s-1)} disabled={busy||step===0}>← 上一步</button><button type="button" className={styles.primary} disabled={busy||!valid} onClick={()=>last?onComplete(answers as AssessmentAnswers):setStep(s=>s+1)}>{busy?'正在整理…':last?'生成我的方案':'继续'}<Icon name="arrow" size={15}/></button></div>
    <div className={styles.questionNote}><small>回答用于本次对话，不会改写个人画像。</small><button type="button" disabled={busy} onClick={onCancel}>先直接聊聊</button></div>
  </section>;
}

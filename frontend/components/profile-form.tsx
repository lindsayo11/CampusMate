"use client";

import {useState, type FormEvent} from 'react';
import {apiBase, type Profile} from '@/lib/api';
import {streams, Icon} from '@/components/ui';
import s from './settings-studio.module.css';

export function ProfileForm({initial, onSaved}: {initial: Profile; onSaved?: (profile: Profile) => void}) {
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    const text = (key: string) => String(data.get(key) || '').trim();
    const list = (key: string) => text(key).split(/[,，]/).map(x => x.trim()).filter(Boolean);
    const payload = {
      display_name: text('display_name'), discoverable: data.get('discoverable') === 'on',
      school: text('school'), college: text('college'), grade: text('grade'), major: text('major'),
      interests: list('interests'), skills: list('skills'), weekly_hours: Number(data.get('weekly_hours')),
      degree: text('degree'), target_year: data.get('target_year') ? Number(data.get('target_year')) : null,
      target_path: text('target_path'), target_region: text('target_region'), language_score: text('language_score'),
      research_exp: text('research_exp'), internship_exp: text('internship_exp'),
      competition_exp: text('competition_exp'), startup_exp: text('startup_exp'),
    };
    setSaved(false); setError(''); setBusy(true);
    try {
      const response = await fetch(apiBase + '/v1/profile', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
      const body = await response.json();
      if (!response.ok) throw Error(typeof body.detail === 'string' ? body.detail : '保存失败，请检查填写内容');
      onSaved?.({...initial, ...payload});
      setSaved(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '保存失败，请重试'); }
    finally { setBusy(false); }
  }

  return <form className={s.profileForm} onSubmit={submit} onChange={() => setSaved(false)}>
    <section className={s.card}>
      <header><span className={s.sectionNumber}>01</span><div><h2>学业坐标</h2><p>你现在所处的位置</p></div></header>
      <div className={s.fieldGrid}>
        <label>展示昵称<input name="display_name" required maxLength={40} defaultValue={initial.display_name}/></label>
        <label>学校<input name="school" required maxLength={120} defaultValue={initial.school}/></label>
        <label>学院<input name="college" maxLength={120} defaultValue={initial.college}/></label>
        <label>专业<input name="major" maxLength={120} defaultValue={initial.major}/></label>
        <label>年级<select name="grade" defaultValue={initial.grade}>{Array.from(new Set([initial.grade,'大一','大二','大三','大四','应届生','研究生'])).filter(Boolean).map(x=><option key={x}>{x}</option>)}</select></label>
        <label>学历<select name="degree" defaultValue={initial.degree}>{Array.from(new Set([initial.degree,'专科','本科','硕士','博士'])).filter(Boolean).map(x=><option key={x}>{x}</option>)}</select></label>
      </div>
    </section>
    <section className={s.card}>
      <header><span className={s.sectionNumber}>02</span><div><h2>下一站</h2><p>把方向变得更具体</p></div></header>
      <div className={s.fieldGrid}>
        <label>目标方向<select name="target_path" defaultValue={initial.target_path}><option value="">尚未确定</option>{initial.target_path&&!streams.some(x=>x.code===initial.target_path)&&<option value={initial.target_path}>{initial.target_path}</option>}{streams.map(x=><option key={x.code} value={x.code}>{x.name}</option>)}</select></label>
        <label>目标年份<input name="target_year" type="number" min={2020} max={2100} defaultValue={initial.target_year??''} placeholder="例如 2027"/></label>
        <label>目标地区<input name="target_region" maxLength={80} defaultValue={initial.target_region} placeholder="广东、上海…"/></label>
        <label>语言成绩<input name="language_score" maxLength={80} defaultValue={initial.language_score} placeholder="CET-6 / IELTS…"/></label>
      </div>
      <div className={s.quietNote}><Icon name="spark" size={18}/><span>目标可以随时调整。</span></div>
    </section>
    <section className={s.card+' '+s.fullWidth}>
      <header><span className={s.sectionNumber}>03</span><div><h2>你的经历，有迹可循</h2><p>记录实际参与的项目与成果，用于资格核对</p></div></header>
      <div className={s.fieldGrid}>
        <label>科研经历<textarea name="research_exp" rows={3} maxLength={2000} defaultValue={initial.research_exp} placeholder="研究方向、承担工作与成果…"/></label>
        <label>实习经历<textarea name="internship_exp" rows={3} maxLength={2000} defaultValue={initial.internship_exp} placeholder="岗位、职责与收获…"/></label>
        <label>竞赛经历<textarea name="competition_exp" rows={3} maxLength={2000} defaultValue={initial.competition_exp} placeholder="赛事、组别与奖项…"/></label>
        <label>创业经历<textarea name="startup_exp" rows={3} maxLength={2000} defaultValue={initial.startup_exp} placeholder="项目阶段、分工与验证…"/></label>
      </div>
    </section>
    <section className={s.card+' '+s.fullWidth}>
      <header><span className={s.sectionNumber}>04</span><div><h2>一起行动的可能</h2><p>技能与组队偏好</p></div></header>
      <div className={s.collaborationFields}>
        <label>兴趣<input name="interests" maxLength={300} defaultValue={initial.interests.join('，')} placeholder="多个兴趣用逗号分隔"/></label>
        <label>技能<input name="skills" maxLength={300} defaultValue={initial.skills.join('，')} placeholder="多个技能用逗号分隔"/></label>
        <label>每周投入 / 小时<input name="weekly_hours" type="number" min={0} max={80} defaultValue={initial.weekly_hours}/></label>
      </div>
      <label className={s.discoverable}><input type="checkbox" name="discoverable" defaultChecked={initial.discoverable}/><span>允许同校同学通过技能匹配找到我<small>公开昵称、技能和可投入时间；学校信息为自行填写，尚未核验学籍。</small></span></label>
    </section>
    <footer className={s.saveBar}>
      <div aria-live="polite">{error ? <p className={s.error} role="alert">{error}</p> : saved ? <p className={s.saved}>画像已保存，可用于资格核对。</p> : <span>修改完成后，保存你的个人画像。</span>}</div>
      <button className={s.primary} disabled={busy} type="submit"><Icon name="check" size={17}/>{busy?'保存中…':'保存画像'}</button>
    </footer>
  </form>;
}

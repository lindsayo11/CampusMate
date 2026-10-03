"use client";
import {useState} from 'react';
import {apiBase} from '@/lib/api';
import {PageHeading,Icon} from '@/components/ui';
import {SourceCitations,type Citation} from '@/components/source-citations';
export default function Knowledge(){
 const [query,setQuery]=useState('报名材料'),[kind,setKind]=useState(''),[items,setItems]=useState<Citation[]>([]),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 return <div className="shell page narrow"><PageHeading eyebrow="SOURCE LIBRARY" title="查找原文依据" description="检索公开且仍有效的原文片段，回到信息本身核对申请要求。"/><form className="form-card" onSubmit={async e=>{e.preventDefault();if(busy)return;setBusy(true);setItems([]);setMessage('检索中…');try{const r=await fetch(apiBase+'/v1/knowledge/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query,type:kind||null,limit:5})});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'请输入有效关键词');setItems(d.items);setMessage(d.message+(d.candidate_limit_reached?'，结果较多，请增加关键词或选择板块缩小范围。':''))}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}}>
 <label>要查找的内容<input value={query} onChange={e=>setQuery(e.target.value)} minLength={2} maxLength={200} required/></label><label>板块<select value={kind} onChange={e=>setKind(e.target.value)}><option value="">全部</option>{[['job','就业'],['contest','竞赛'],['civil_service','考公'],['volunteer','志愿'],['club','社团'],['graduate','升学']].map(([v,t])=><option key={v} value={v}>{t}</option>)}</select></label><button disabled={busy}>{busy?'检索中…':'检索依据'}</button></form><p role="status">{message}</p><SourceCitations items={items}/></div>;
}

import type {Opportunity} from './api';

export const sourceTypes: Record<string, string> = {
  graduate:'升学资料', university_notice:'高校通知', education_policy:'教育政策',
  contest:'竞赛项目', job:'实习就业', civil_service:'考公考编', policy:'政策参考',
  volunteer:'志愿活动', club:'社团活动', campus:'校园资讯', calendar:'考试日程', reference:'参考资料',
};
export type SourceDocument = {
  document_id:string; title:string; type:string; source_url:string; fetched_at:string;
  content_hash:string; excerpt:string; chunk_count:number; opportunity_id:string|null;
};
export type SourceDirectory = {
  items:SourceDocument[]; total:number; library_total:number; chunk_total:number;
  by_type:Record<string,number>; offset:number; limit:number;
};
export type SourceReading = SourceDocument & {text:string; display_text?:string; is_formatted?:boolean; truncated:boolean; character_count:number};
export type EligibilityOption = Omit<Opportunity,'deadline'> & {
  deadline:string|null; rule_count:number; pending_count:number;
  rules:{label:string;field:string;expected:string;evidence:string;source_url:string;supported:boolean}[];
};
export type EligibilityOptions = {items:EligibilityOption[]; total:number; with_rules:number};
export class WorkspaceRequestError extends Error {
  constructor(message:string,public status:number){super(message);}
}
export async function evidenceRequest<T>(path:string,options:RequestInit={}):Promise<T>{
  const response=await fetch('/api/backend'+path,{cache:'no-store',...options});
  const value=await response.json().catch(()=>null);
  if(!response.ok)throw new WorkspaceRequestError(
    response.status===401?'请登录后查看此内容':response.status===403?'当前账号没有访问权限':
    typeof value?.detail==='string'?value.detail:'内容暂时无法加载，请重试',response.status);
  return value as T;
}
export function externalUrl(value?:string|null){try{const url=new URL(value||'');return ['https:','http:'].includes(url.protocol)?url.href:undefined;}catch{return undefined;}}
export function sourceHost(value:string){try{return new URL(value).hostname;}catch{return '来源待确认';}}
export function archiveDate(value?:string|null){
  if(!value)return '日期未注明';
  const date=new Date(value);return Number.isFinite(date.getTime())?
    date.toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}):'日期待核对';
}

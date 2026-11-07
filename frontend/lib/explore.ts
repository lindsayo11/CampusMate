import type {CatalogItem} from './catalog';

export const availabilityLabels:Record<string,string>={
  open:'正在开放',upcoming:'即将开始',expired:'已截止',needs_confirmation:'报名时间待核验',
  reference:'参考资料',report:'活动报道',
};
export const teamLabels:Record<string,string>={none:'暂无队伍',recruiting:'招募中',full:'已满员',closed:'暂停招募',joined:'我已加入'};
export function safeSourceUrl(value:unknown):string|undefined{
  if(typeof value!=='string')return;
  try{const url=new URL(value);if(['https:','http:'].includes(url.protocol)&&!url.username&&!url.password)return url.href;}catch{}
}
export function noticeDate(value?:string|null){
  if(!value)return '待核验';
  const date=new Date(value);
  return Number.isNaN(date.getTime())?'待核验':date.toLocaleDateString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'Asia/Shanghai'});
}
export function noticeSummary(item:Pick<CatalogItem,'description'|'ai_summary'>){
  return (item.ai_summary||item.description||'打开公告查看已收录的内容与来源。').replace(/\s+/g,' ').slice(0,180);
}

export type NoticeItem=CatalogItem&{materials?:(string|{title:string;url?:string})[];cycle_id?:string};
export type Publication={
  id:string;items:NoticeItem[];
  source:{name:string;publisher?:string;region_code?:string};
  document:{canonical_url:string;version_no:number;fetched_at:string;publish_time?:string;import_mode?:string};
  positions:{id:string;title:string;organization:string;education:string;majors:string;headcount:number;remarks:string}[];
  rules:{id:number;target_id:string;label:string;expected:string;evidence_id:string}[];
  evidence:{id:string;quote_or_normalized_fact:string;evidence_location:string}[];
};
export type SourceText={text:string;url:string;version:number;fetched_at:string;truncated:boolean;source:string};

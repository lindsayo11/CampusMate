// One source of truth for channel identity; URL query parameters cannot switch a dedicated channel.
export const developmentChannels = [
  {code:'recommendation_exemption',name:'保研推免',description:'关注推免政策、夏令营与院校接收通知。',searchPlaceholder:'搜索推免通知、夏令营或院校'},
  {code:'domestic_postgraduate_exam',name:'国内考研',description:'查阅招生简章、专业目录与考试安排。',searchPlaceholder:'搜索招生简章、专业或院校'},
  {code:'overseas_study',name:'境外留学',description:'发现留学项目、奖学金与申请要求。',searchPlaceholder:'搜索留学项目、奖学金或院校'},
  {code:'national_civil_service',name:'考公考编',description:'查找招录公告、岗位条件与考试节点。',searchPlaceholder:'搜索招录公告、岗位或地区'},
  {code:'employment',name:'实习就业',description:'关注实习、校园招聘与求职机会。',searchPlaceholder:'搜索实习、招聘或企业'},
] as const;

export type DevelopmentChannel = typeof developmentChannels[number];
export type ChannelCode = DevelopmentChannel['code'];
export type CatalogFilters = {q?:string;path?:string;region?:string;offset?:string;status?:string;school?:string;year?:string;kind?:string;sort?:string};

export function getChannel(code?:string|null) {
  return developmentChannels.find(channel=>channel.code===code);
}

export function channelHref(code?:string|null):string {
  if(code==='entrepreneurship')return '/entrepreneurship';
  const channel=getChannel(code);
  return channel ? '/channels/'+channel.code : '/data';
}

// This allow-list also prevents query/path injection when preserving old bookmarks.
export function catalogHref(code:string|undefined,filters:CatalogFilters={}):string {
  const channel=getChannel(code);
  const query=new URLSearchParams();
  for(const key of ['q','region','offset','status','school','year','kind','sort'] as const) {
    const value=filters[key];
    if(typeof value==='string'&&value)query.set(key,value);
  }
  if(!channel&&filters.path==='entrepreneurship')query.set('path','entrepreneurship');
  const base=channelHref(channel?.code);
  return base+(query.size?'?'+query:'');
}

export function currentChannel(pathname:string,params:{get:(key:string)=>string|null}):DevelopmentChannel|undefined {
  const segment=pathname.match(/^\/channels\/([^/]+)\/?$/)?.[1];
  if(segment)return getChannel(segment);
  if(pathname==='/data')return getChannel(params.get('path'));
  if(/^\/data\/[^/]+$/.test(pathname)&&pathname!=='/data/timeline')return getChannel(params.get('channel'));
}

export function noticeHref(publicationId:string,itemId?:string,channel?:string):string {
  const query=new URLSearchParams();
  if(itemId)query.set('item',itemId);
  const context=getChannel(channel);
  if(context)query.set('channel',context.code);
  return '/data/'+encodeURIComponent(publicationId)+(query.size?'?'+query:'');
}

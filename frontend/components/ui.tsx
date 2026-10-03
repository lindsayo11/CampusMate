import Link from "next/link";
import type {CSSProperties, ReactNode} from "react";

export type IconName = "home"|"search"|"bell"|"book"|"check"|"users"|"spark"|"arrow"|"plus"|"close"|"menu"|"calendar"|"settings"|"shield"|"logout"|"chevron"|"hash"|"send"|"file"|"clock"|"filter"|"link";
const lines: Record<IconName, ReactNode> = {
 home:<><path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/></>,
 search:<><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
 bell:<><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Z"/><path d="M10 21h4"/></>,
 book:<><path d="M12 5v16M3 3l9 2 9-2v16l-9 2-9-2Z"/></>,
 check:<><rect x="3" y="3" width="18" height="18" rx="4"/><path d="m7 12 3 3 7-7"/></>,
 users:<><circle cx="9" cy="8" r="3"/><path d="M2 21v-3a7 7 0 0 1 14 0v3M16 5a3 3 0 0 1 0 6m3 3a5 5 0 0 1 3 4v3"/></>,
 spark:<><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5ZM20 2v4m-2-2h4"/></>,
 arrow:<path d="M4 12h16m-6-6 6 6-6 6"/>, plus:<path d="M12 5v14M5 12h14"/>,close:<path d="m6 6 12 12M6 18 18 6"/>,
 menu:<path d="M4 6h16M4 12h16M4 18h16"/>,calendar:<><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6m10-6v6M3 11h18m-14 5h3m4 0h3"/></>,
 settings:<><path d="m9 3-1 3-3 1v4l-2 1 2 2v4l3 1 1 2h5l1-3 4-1v-3l2-2-2-2V7l-4-1-1-3Z"/><circle cx="12" cy="12" r="3"/></>,
 shield:<><path d="m12 2 9 4v6c0 6-9 10-9 10S3 18 3 12V6Z"/><path d="m8 12 3 3 5-6"/></>,
 logout:<path d="M9 3H3v18h6m6-14 5 5-5 5m-7-5h12"/>,chevron:<path d="m9 5 7 7-7 7"/>,
 hash:<path d="m9 3-2 18m10-18-2 18M3 8h18M2 16h18"/>,send:<><path d="m3 3 19 9-19 9 3-9Z"/><path d="M6 12h16"/></>,
 file:<><path d="M5 2h9l5 5v15H5ZM14 2v6h5M8 12h8m-8 4h6"/></>,clock:<><circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/></>,
 filter:<path d="M3 5h18M6 12h12m-9 7h6"/>,link:<><path d="m10 7 3-3a5 5 0 0 1 7 7l-3 3M14 17l-3 3a5 5 0 0 1-7-7l3-3m1 9 8-8"/></>,
};
export function Icon({name,size=18}:{name:IconName;size?:number}) {return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{lines[name]}</svg>}
export const streams = [
 {code:"recommendation_exemption",name:"保研推免",color:"#568f6c",note:"成绩、科研与申请准备"},
 {code:"domestic_postgraduate_exam",name:"国内考研",color:"#4b8eb6",note:"院校信息与备考节点"},
 {code:"overseas_study",name:"境外留学",color:"#8b78b0",note:"项目选择与申请材料"},
 {code:"national_civil_service",name:"考公考编",color:"#c18b46",note:"岗位、资格与考试安排"},
 {code:"employment",name:"实习就业",color:"#5a9eab",note:"实习、招聘与求职准备"},
 {code:"entrepreneurship",name:"创新创业",color:"#bb7789",note:"项目验证与支持政策"},
];
export function PageHeading({eyebrow,title,description,children}:{eyebrow?:string;title:string;description?:string;children?:ReactNode}){return <header className="page-heading"><div>{eyebrow&&<p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description&&<p className="lead">{description}</p>}</div>{children&&<div className="heading-actions">{children}</div>}</header>}
export function TopicBar({title,color="#4b8eb6",children}:{title:string;color?:string;children?:ReactNode}){return <div className="topic-bar" style={{"--topic-color":color} as CSSProperties}><span className="topic-label"><Icon name="hash" size={15}/>{title}</span>{children&&<span className="topic-extra">{children}</span>}</div>}
export function EmptyState({title,description,href,label,icon="search"}:{title:string;description?:string;href?:string;label?:string;icon?:IconName}){return <div className="empty-state"><span className="empty-icon"><Icon name={icon} size={25}/></span><h3>{title}</h3>{description&&<p>{description}</p>}{href&&<Link className="button secondary" href={href}>{label||"去看看"}<Icon name="arrow" size={15}/></Link>}</div>}
export function ContextRail({children}:{children:ReactNode}){return <aside className="context-rail" aria-label="相关信息">{children}</aside>}
export function dateLabel(value:string|null|undefined){if(!value)return "未注明日期";const d=new Date(value);return Number.isNaN(d.getTime())?"日期待核对":d.toLocaleDateString("zh-CN",{month:"short",day:"numeric",timeZone:"Asia/Shanghai"})}

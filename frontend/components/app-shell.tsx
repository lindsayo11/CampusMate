"use client";
import Link from "next/link";
import {usePathname,useSearchParams} from "next/navigation";
import {useEffect,useRef,useState,type ReactNode} from "react";
import {Icon,streams,type IconName} from "@/components/ui";

type Props={children:ReactNode;demo:boolean|null;admin:boolean;name:string;school:string;authenticated:boolean;agentEnabled:boolean};
const primary:[string,string,IconName][]=[["/","工作台","home"],["/data","信息中心","search"],["/tracker","我的计划","check"],["/notifications","通知中心","bell"]];
const adminLinks=[["/admin","运营概览"],["/admin/data","数据接入与发布"],["/admin/notice-watch","官方栏目监测"],["/admin/registry","数据源管理"],["/admin/review","内容审核"],["/admin/sources","人工导入"],["/admin/source-candidates","来源候选"],["/admin/source-changes","来源变更"],["/admin/overseas","留学信息审核"],["/admin/entrepreneurship","创业政策审核"],["/admin/reports","举报处理"],["/admin/audit","操作审计"],["/admin/operations","运行状态"]];
export function AppShell({children,demo,admin,name,school,authenticated,agentEnabled}:Props){
 const pathname=usePathname();const params=useSearchParams();const selectedStream=params.get("path")||"";const [open,setOpen]=useState(false),[mobile,setMobile]=useState(false);const search=useRef<HTMLInputElement>(null),menu=useRef<HTMLButtonElement>(null),sidebar=useRef<HTMLElement>(null);
 useEffect(()=>{setOpen(false)},[pathname,selectedStream]);
 useEffect(()=>{const shortcut=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key==="k"){e.preventDefault();search.current?.focus()}if(e.key==="Escape"&&open){setOpen(false);menu.current?.focus()}};window.addEventListener("keydown",shortcut);return ()=>window.removeEventListener("keydown",shortcut)},[open]);
 useEffect(()=>{if(!open)return;sidebar.current?.querySelector<HTMLAnchorElement>("a")?.focus();const previous=document.body.style.overflow;document.body.style.overflow="hidden";const trap=(e:KeyboardEvent)=>{if(e.key!=="Tab")return;const nodes=[menu.current,...Array.from(sidebar.current?.querySelectorAll<HTMLElement>('a[href],button:not([disabled])')||[])].filter(Boolean) as HTMLElement[];const index=nodes.indexOf(document.activeElement as HTMLElement);const next=e.shiftKey?(index<=0?nodes.length-1:index-1):(index+1)%nodes.length;e.preventDefault();nodes[next]?.focus();};window.addEventListener("keydown",trap);return ()=>{document.body.style.overflow=previous;window.removeEventListener("keydown",trap)}},[open]);
 useEffect(()=>{const media=window.matchMedia("(min-width: 761px)");const reset=()=>{setMobile(!media.matches);if(media.matches)setOpen(false)};reset();media.addEventListener("change",reset);return ()=>media.removeEventListener("change",reset)},[]);
 const isAdmin=admin&&pathname.startsWith("/admin");
 function nav(href:string,label:string,icon:IconName){const active=href==="/"?pathname==="/":href==="/data"?pathname.startsWith("/data"):pathname===href;return <Link key={href} href={href} className={`nav-item ${active?"selected":""}`} aria-current={active?"page":undefined} onClick={()=>{setOpen(false)}}><Icon name={icon}/><span>{label}</span></Link>}
 return <div className="app-frame"><a className="skip-link" href="#main-content">跳转到主要内容</a>
  <header className="workspace-topbar"><button ref={menu} className="icon-button menu-toggle" aria-label={open?"收起导航":"展开导航"} aria-expanded={open} aria-controls="workspace-navigation" onClick={()=>setOpen(!open)}><Icon name={open?"close":"menu"}/></button><Link className="workspace-brand" href="/"><span className="brand-mark">C<span>m</span></span><strong>CampusMate <small>校伴</small></strong></Link><span className="workspace-name">学生发展空间</span><form className="global-search" action="/data" role="search"><Icon name="search" size={17}/><input ref={search} aria-label="搜索全站信息" name="q" placeholder="搜索机会、院校与政策…" maxLength={100}/><kbd>⌘ K</kbd><button className="sr-only">搜索信息</button></form><Link href="/notifications" className="topbar-icon" aria-label="查看通知"><Icon name="bell"/></Link><Link className="user-avatar topbar-avatar" href={authenticated?"/profile":"/login"} aria-label={authenticated?"个人中心":"登录"}>{authenticated?name.slice(0,1):"我"}</Link></header>
  {open&&<button className="nav-overlay" aria-label="关闭导航" onClick={()=>setOpen(false)} tabIndex={-1}/>}
  <aside className={`workspace-sidebar ${open?"is-open":""}`} id="workspace-navigation" ref={sidebar} inert={mobile&&!open} role={mobile&&open?"dialog":undefined} aria-modal={mobile&&open?true:undefined} aria-label="站点导航">
   <div className="space-label"><span className="space-monogram">{isAdmin?"管":"校"}</span><div><b>{isAdmin?"运营管理空间":"我的校园空间"}</b><small>{isAdmin?"管理员工作视图":demo?"演示 · 学生工作视图":"学生工作视图"}</small></div></div>
   <nav aria-label="主导航">{isAdmin?<><Link className="nav-item return-workspace" href="/"><Icon name="arrow"/><span>返回学生工作台</span></Link><div className="nav-section-title">运营管理 · 仅管理员</div>{adminLinks.map(([href,label])=><Link key={href} href={href} className={`nav-item ${pathname===href?"selected":""}`} aria-current={pathname===href?"page":undefined} onClick={()=>setOpen(false)}><Icon name={href==="/admin"?"home":href.includes("review")?"shield":href.includes("operations")?"settings":"file"}/><span>{label}</span></Link>)}</>:<>{primary.map(([h,l,i])=>nav(h,l,i))}
    <div className="nav-section-title">发展频道<Link href="/paths" aria-label="查看全部发展路径"><Icon name="plus" size={14}/></Link></div>
    {streams.map(s=><Link href={`/data?path=${s.code}`} key={s.code} className={`stream-item ${pathname==="/data"&&selectedStream===s.code?"active":""}`} aria-current={pathname==="/data"&&selectedStream===s.code?"page":undefined} onClick={()=>{setOpen(false)}}><span className="stream-dot" style={{background:s.color}}/>{s.name}<Icon name="chevron" size={12}/></Link>)}
    <div className="nav-section-title">探索与协作</div>
    {nav("/startup","创业工作台","spark")}{nav("/opportunities","校园机会","calendar")}{nav("/teams","交流空间","users")}{nav("/team-manager","我的团队","hash")}
    {agentEnabled&&nav("/agent","校伴助手","spark")}{nav("/knowledge","原文资料库","book")}{nav("/eligibility","资格核对","shield")}
    {admin&&<><div className="nav-section-title">管理员专属</div>{nav("/admin","进入运营后台","settings")}</>}</>}
   </nav>
   <div className="sidebar-bottom"><Link href="/safety"><Icon name="shield" size={14}/>隐私与安全</Link><Link href="/login"><Icon name="logout" size={14}/>{authenticated?"账号管理":"登录 / 注册"}</Link></div>
   <Link className="sidebar-profile" href={authenticated?"/profile":"/login"}><span className="user-avatar">{name.slice(0,1)}</span><span><b>{name}<em className="role-label">{admin?"管理员":authenticated?"学生":"访客"}</em></b><small>{school||"完善你的个人资料"}</small></span><Icon name="settings" size={16}/></Link>
  </aside>
  <div className="workspace-body"><div className={`environment-strip ${demo===null?"unavailable":""}`}><span className="status-dot"/>{demo===true?"本地预览 · 演示账号，信息请核对原文":demo===false?"信息保留来源与版本，申请前请核对官方原文":"服务暂时未连接，部分内容可能无法加载"}<Link href={demo===true?"/safety":"/knowledge"}>{demo===true?"查看说明":"原文依据"}<Icon name="arrow" size={12}/></Link></div><main id="main-content" tabIndex={-1}>{children}</main><footer className="workspace-footer"><span>CampusMate 校伴</span><span>每一个方向，都从下一步开始。</span></footer></div>
 </div>
}

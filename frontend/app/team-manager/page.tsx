"use client";
import {useEffect,useState} from "react";
import Link from "next/link";
import {TeamTaskBoard} from "@/components/team-task-board";
import {TeamJoinRequests} from "@/components/activity-teams";
import {apiBase} from "@/lib/api";
import {HugeIcon,Icon,PageHeading} from "@/components/ui";

type Team={id:string;title:string;members:string[];room_id:string;owner:string;capacity:number;is_owner:boolean};
type Invite={team_id:string;status:string;title:string;team_status:string};

async function callApi(path:string,data?:unknown){
  const response=await fetch(apiBase+path,data===undefined?{cache:"no-store"}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
  if(!response.ok){const detail=await response.json().catch(()=>null);throw new Error(typeof detail?.detail==="string"?detail.detail:"输入无效或操作失败")}
  return response.json();
}

export default function Manager(){
  const [teams,setTeams]=useState<Team[]>([]),[invites,setInvites]=useState<Invite[]>([]),[status,setStatus]=useState(""),[myId,setMyId]=useState(""),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true);
  async function refresh(){setTeams(await callApi("/v1/teams"));setInvites(await callApi("/v1/invitations"))}
  async function run(action:()=>Promise<void>){if(busy)return;setBusy(true);try{setStatus("");await action();await refresh()}catch(error){setStatus((error as Error).message)}finally{setBusy(false)}}
  useEffect(()=>{callApi("/v1/profile").then(profile=>setMyId(profile.user_id)).catch(()=>{});refresh().catch(()=>setStatus("请登录后读取团队")).finally(()=>setLoading(false))},[]);

  return <div className="shell team-manager">
    <PageHeading title="团队管理"><Link className="button secondary" href="/teams"><Icon name="users" size={15}/>进入交流空间</Link></PageHeading>
    {loading&&<p role="status">正在加载团队…</p>}
    <TeamJoinRequests onChange={refresh}/>
    <fieldset disabled={busy} className="team-manager-fields">
      <form className="form-card create-team-form" onSubmit={event=>{event.preventDefault();const form=new FormData(event.currentTarget);void run(async()=>{await callApi("/v1/teams",{title:form.get("title"),capacity:Number(form.get("capacity"))})})}}>
        <label>新队伍名称<input name="title" required maxLength={100}/></label>
        <label>人数上限（含队长）<input name="capacity" type="number" min={2} max={20} defaultValue={5} required/></label>
        <button>创建队伍</button>
      </form>

      <div className="team-overview-grid">
        <section className="team-panel" aria-labelledby="team-invites-title">
          <div className="team-panel-heading"><div className="team-panel-title"><span className="team-panel-icon"><HugeIcon name="mail" size={20}/></span><div><h2 id="team-invites-title">收到的邀请</h2><p>等待你确认加入的团队</p></div></div><span className="badge">{invites.length}</span></div>
          <div className="team-panel-body">{!loading&&!invites.length?<div className="team-empty"><HugeIcon name="mail" size={30}/><strong>暂无邀请</strong><span>新的团队邀请会显示在这里</span></div>:<div className="team-invite-list">{invites.map(invite=><article className="team-invite-card" key={invite.team_id}><div><strong>{invite.title}</strong><small>{invite.status}</small></div>{invite.status==="pending"&&invite.team_status==="active"&&<div className="team-invite-actions">{["accept","reject"].map(action=><button key={action} onClick={()=>void run(async()=>{await callApi(`/v1/invitations/${invite.team_id}/decision`,{action})})}>{action==="accept"?"接受":"拒绝"}</button>)}</div>}</article>)}</div>}</div>
        </section>
        <section className="team-panel" aria-labelledby="my-teams-title">
          <div className="team-panel-heading"><div className="team-panel-title"><span className="team-panel-icon team-panel-icon-green"><Icon name="users" size={20}/></span><div><h2 id="my-teams-title">我的队伍</h2><p>你正在参与的协作空间</p></div></div><span className="badge">{teams.length}</span></div>
          <div className="team-panel-body">{!loading&&!teams.length?<div className="team-empty"><Icon name="users" size={30}/><strong>暂无队伍</strong><span>创建队伍或接受邀请后开始协作</span></div>:<div className="team-panel-summary">{teams.length} 个协作空间正在运行</div>}</div>
        </section>
      </div>

      <div className="team-cards">{teams.map(team=><article className="card" id={`team-${team.id}`} key={team.id}><div className="team-card-heading"><div><h3>{team.title}</h3><p>{team.members.length} / {team.capacity} 位成员</p></div><span className="badge">{team.is_owner?"队长":"成员"}</span></div>{team.is_owner&&<form onSubmit={event=>{event.preventDefault();const form=new FormData(event.currentTarget);const target=String(form.get("target")||"").trim();const email=String(form.get("email")||"").trim();if(!target&&!email){setStatus("请输入成员邮箱或用户 ID");return}void run(async()=>{await callApi(`/v1/teams/${team.id}/invitations`,{...(target?{target}:{}),...(email?{email}:{})});setStatus("邀请已发送")})}}><label>成员登录邮箱<input name="email" type="email" maxLength={320} placeholder="优先使用邮箱查找"/></label><label>或用户 ID<input name="target" maxLength={80}/></label><button>邀请成员</button></form>}<ul>{team.members.map(member=><li key={member}>{member}{member===team.owner?"（队长）":team.is_owner&&<button onClick={()=>{if(window.confirm("确认移除此成员？"))void run(async()=>{await callApi(`/v1/teams/${team.id}/remove`,{target:member})})}}>移除</button>}</li>)}</ul><TeamTaskBoard teamId={team.id} members={team.members} owner={team.is_owner} myId={myId}/><a href={`/teams?room=${encodeURIComponent(team.room_id)}`}>进入队伍房间</a><p><button className="danger" onClick={()=>{if(window.confirm(team.is_owner?"解散后所有成员将失去房间访问权，确认解散？":"确认退出队伍？"))void run(async()=>{await callApi(`/v1/teams/${team.id}/${team.is_owner?"dissolve":"leave"}`,{})})}}>{team.is_owner?"解散队伍":"退出队伍"}</button></p></article>)}</div>
    </fieldset>
    <p role="status">{status}</p>
  </div>;
}

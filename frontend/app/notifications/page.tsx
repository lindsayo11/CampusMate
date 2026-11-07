import {ReminderList} from '@/components/reminder-list';
import {privateApi} from '@/lib/session-api';
import {TaskAlertList} from '@/components/task-alert-list';
import {NotificationList} from '@/components/notification-list';
import {DataAlerts} from '@/components/data-follow';
import {PlanReminderPanel} from '@/components/plan-reminders';
import {Icon} from '@/components/ui';
import Link from 'next/link';

export default async function Notifications(){
  const [rows,tasks,reminders,data,preferences]=await Promise.all([privateApi('/v1/notifications'),privateApi('/v1/task-alerts'),privateApi('/v1/reminders'),privateApi('/v1/data/subscriptions'),privateApi('/v1/notification-preferences')]);
  const taskItems=Array.isArray(tasks?.items)?tasks.items:[];
  const sourceItems=Array.isArray(data)?data:[];
  const deadlineItems=Array.isArray(rows)?rows:[];
  const reminderItems=Array.isArray(reminders)?reminders:[];
  const sourceUpdatesEnabled=preferences?.source_updates!==false;
  const sourceVisibleItems=sourceUpdatesEnabled?sourceItems:sourceItems.filter((item:{status?:string})=>item.status!=='source_changed');
  const sourceUnread=sourceUpdatesEnabled?sourceVisibleItems.filter((item:{read_at?:string|null})=>!item.read_at).length:0;
  const taskUnread=taskItems.filter((item:{read_at?:string|null})=>!item.read_at).length;
  const deadlineUnread=deadlineItems.filter((item:{read_at?:string|null})=>!item.read_at).length;
  const opportunityUnread=deadlineUnread+reminderItems.filter((item:{sent?:boolean})=>!item.sent).length;
  const unreadTotal=sourceUnread+taskUnread+opportunityUnread;
  const count=(value:number)=>value>99?'99+':String(value);
  return <div className="shell notifications-page">
    <header className="notifications-hero"><div className="notifications-hero-title"><span className="notifications-hero-icon"><Icon name="bell" size={24}/></span><div><p className="eyebrow">ACTIVITY</p><h1>通知中心</h1></div></div><div className="notifications-hero-actions"><span className={unreadTotal?'notifications-unread':'notifications-unread is-clear'}><i aria-hidden="true"/>{unreadTotal?`${count(unreadTotal)} 条未读`:'暂无未读'}</span></div></header>
    <nav className="notifications-summary-strip" aria-label="通知分类"><a href="#personal"><span className="notifications-summary-icon is-blue"><Icon name="check" size={17}/></span><span><strong>个人计划</strong><small>计划提醒</small></span><b>—</b></a><a href="#sources"><span className="notifications-summary-icon is-purple"><Icon name="bell" size={17}/></span><span><strong>关注事项</strong><small>信息变化</small></span><b>{count(sourceUnread)}</b></a><a href="#team"><span className="notifications-summary-icon is-amber"><Icon name="users" size={17}/></span><span><strong>团队任务</strong><small>协作提醒</small></span><b>{count(taskUnread)}</b></a><a href="#opportunity"><span className="notifications-summary-icon is-green"><Icon name="calendar" size={17}/></span><span><strong>校园机会</strong><small>截止提醒</small></span><b>{count(opportunityUnread)}</b></a></nav>
    <div className="notifications-content"><section className="notifications-stream-panel" aria-label="最新通知"><header className="notifications-stream-heading"><div><p className="eyebrow">INBOX</p><h2>最新动态</h2></div><span>{unreadTotal?`${count(unreadTotal)} 条未读`:'全部已读'}</span></header><div className="notifications-stack">
      <section className="notification-section-card" id="personal"><header><span className="notification-section-icon is-blue"><Icon name="check" size={17}/></span><div><h3>个人计划</h3><small>来自计划与提醒</small></div></header><div className="notification-section-body"><PlanReminderPanel/></div></section>
      <section className="notification-section-card" id="sources"><header><span className="notification-section-icon is-purple"><Icon name="bell" size={17}/></span><div><h3>关注事项</h3><small>来源内容有新变化时显示</small></div></header><div className="notification-section-body"><DataAlerts initial={sourceItems} sourceUpdatesEnabled={sourceUpdatesEnabled}/></div></section>
      <section className="notification-section-card" id="team"><header><span className="notification-section-icon is-amber"><Icon name="users" size={17}/></span><div><h3>团队任务</h3><small>协作中的任务提醒</small></div></header><div className="notification-section-body"><TaskAlertList initial={tasks}/></div></section>
      <section className="notification-section-card" id="opportunity"><header><span className="notification-section-icon is-green"><Icon name="calendar" size={17}/></span><div><h3>校园机会</h3><small>报名与截止日期</small></div></header><div className="notification-section-body"><ReminderList initial={reminders}/><div className="notification-subsection"><h4>报名截止提醒</h4><NotificationList initial={rows}/></div></div></section>
    </div></section></div>
  </div>;
}

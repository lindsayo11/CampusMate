'use client';

import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useEffect, useMemo, useRef, useState, useTransition, type KeyboardEvent} from 'react';
import {Icon, streams} from './ui';
import {addDays, dateRange, dayTime, eventStatus, initialMonth, kindLabels, monthBounds, monthWeeks, overlaps, shiftMonth, weekSegments, type CalendarData, type CalendarEvent} from '@/lib/calendar';
import s from './development-calendar.module.css';

const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const MAX_LANES = 3;
function Star({filled = false}: {filled?: boolean}) {
  return <svg width="19" height="19" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" aria-hidden="true"><path d="m12 3 2.8 5.7 6.3.9-4.6 4.4 1.1 6.3-5.6-3-5.6 3 1.1-6.3L2.9 9.6l6.3-.9Z"/></svg>;
}
function monthLabel(month: string) { const [y, m] = month.split('-'); return `${y}年${Number(m)}月`; }
function safeOriginalUrl(value?: string) { try { const url = new URL(value || ''); return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined; } catch { return undefined; } }

export function DevelopmentCalendar({data}: {data: CalendarData}) {
  const router = useRouter();
  const [pending, startRefresh] = useTransition();
  const [month, setMonth] = useState(() => initialMonth(data.events, data.today));
  const [query, setQuery] = useState(''), [direction, setDirection] = useState(''), [status, setStatus] = useState('');
  const [year, setYear] = useState(''), [kind, setKind] = useState(''), [onlyFavorites, setOnlyFavorites] = useState(false);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [focusDay, setFocusDay] = useState(() => month + '-01');
  const [detail, setDetail] = useState<CalendarEvent | null>(null);
  const [saved, setSaved] = useState<{owner: string | null; ids: string[]}>({owner: null, ids: []});
  const [favoritesReady, setFavoritesReady] = useState(false), [toast, setToast] = useState('');
  const dialog = useRef<HTMLDialogElement>(null), calendar = useRef<HTMLDivElement>(null), needsFocus = useRef(false);
  const favoriteIds = saved.owner === data.userId ? saved.ids : [];
  const storageKey = data.userId ? `campusmate-calendar-favorites:${data.userId}` : null;

  useEffect(() => {
    setFavoritesReady(false);
    try {
      const parsed: unknown = storageKey ? JSON.parse(localStorage.getItem(storageKey) || '[]') : [];
      setSaved({owner: data.userId, ids: Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === 'string') : []});
    } catch { setSaved({owner: data.userId, ids: []}); setToast('无法读取本浏览器的收藏。'); }
    setFavoritesReady(true);
  }, [storageKey, data.userId]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(''), 3600); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => { if (detail && !dialog.current?.open) dialog.current?.showModal(); }, [detail]);
  useEffect(() => {
    if (!needsFocus.current) return;
    calendar.current?.querySelector<HTMLButtonElement>(`[data-day="${focusDay}"]`)?.focus();
    needsFocus.current = false;
  }, [focusDay, month]);

  const filtered = useMemo(() => data.events.filter(event => {
    const text = [event.title, event.source, event.location, ...event.paths.map(p => p.name)].join(' ').toLocaleLowerCase();
    const pathName = streams.find(p => p.code === direction)?.name;
    const state = eventStatus(event, data.today);
    return (!query.trim() || text.includes(query.trim().toLocaleLowerCase()))
      && (!direction || event.paths.some(p => p.code === direction || p.name === pathName))
      && (!status || state === status)
      && (!year || (event.start.slice(0, 4) <= year && event.end.slice(0, 4) >= year))
      && (!kind || event.kind === kind)
      && (!onlyFavorites || favoriteIds.includes(event.id));
  }), [data.events, data.today, query, direction, status, year, kind, onlyFavorites, favoriteIds]);
  const weeks = monthWeeks(month), bounds = monthBounds(month);
  const monthEvents = filtered.filter(event => overlaps(event, bounds.start, bounds.end));
  const upcoming = filtered.filter(event => event.end >= data.today && event.planStatus !== 'done')
    .sort((a, b) => (a.start < data.today ? a.end : a.start).localeCompare(b.start < data.today ? b.end : b.start)).slice(0, 3);
  const sideEvents = selectedDay ? filtered.filter(event => overlaps(event, selectedDay)) : upcoming;
  const allEvents = [...filtered].sort((a, b) => {
    const aPast = a.end < data.today, bPast = b.end < data.today;
    if (aPast !== bPast) return aPast ? 1 : -1;
    return aPast ? b.end.localeCompare(a.end) : a.start.localeCompare(b.start);
  });
  const years = [...new Set(data.events.flatMap(event => {
    const first = Number(event.start.slice(0, 4)), last = Number(event.end.slice(0, 4));
    return Array.from({length: Math.min(last - first + 1, 100)}, (_, i) => String(first + i));
  }))].sort().reverse();
  const hasFilters = Boolean(query || direction || status || year || kind || onlyFavorites);
  const failed = [data.publicState === 'error' && '公开日程', data.planState === 'error' && '个人计划', data.pathsState === 'error' && '计划方向'].filter(Boolean);
  const unauthorized = data.planState === 'permission' || !data.userId;

  function clearFilters() { setQuery(''); setDirection(''); setStatus(''); setYear(''); setKind(''); setOnlyFavorites(false); setSelectedDay(null); }
  function moveMonth(next: string) { setMonth(next); setSelectedDay(null); setFocusDay(next === data.today.slice(0, 7) ? data.today : next + '-01'); }
  function toggleFavorite(event: CalendarEvent) {
    if (!storageKey || !favoritesReady) { setToast('请登录后收藏日程。'); return; }
    const wasSaved = favoriteIds.includes(event.id);
    const ids = wasSaved ? favoriteIds.filter(id => id !== event.id) : [...favoriteIds, event.id];
    try {
      localStorage.setItem(storageKey, JSON.stringify(ids));
      setSaved({owner: data.userId, ids});
      setToast(wasSaved ? '已取消收藏' : '已收藏 · 保存在本浏览器');
    } catch { setToast('收藏未保存，请检查浏览器存储权限。'); }
  }
  function favoriteButton(event: CalendarEvent) {
    const filled = favoriteIds.includes(event.id);
    return <button className={`${s.starButton} ${filled ? s.starred : ''}`} type="button" aria-label={`${filled ? '取消收藏' : '收藏'}：${event.title}`} aria-pressed={filled} disabled={!data.userId || !favoritesReady} title={data.userId ? '仅保存在当前账号的本浏览器中' : '登录后可收藏'} onClick={() => toggleFavorite(event)}><Star filled={filled}/></button>;
  }
  function selectDay(day: string) { setSelectedDay(day); setFocusDay(day); if (!day.startsWith(month)) setMonth(day.slice(0, 7)); }
  function dayKey(event: KeyboardEvent<HTMLButtonElement>, day: string) {
    const weekday = (new Date(dayTime(day)).getUTCDay() + 6) % 7;
    const steps: Record<string, number> = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -weekday, End: 6 - weekday};
    if (!(event.key in steps)) return;
    event.preventDefault(); const next = addDays(day, steps[event.key]);
    needsFocus.current = true; setFocusDay(next); if (!next.startsWith(month)) setMonth(next.slice(0, 7));
  }
  function openDetail(event: CalendarEvent) { setDetail(event); }

  return <div className={s.page}>
    <header className={s.pageHeader}>
      <div className={s.titleGroup}><span className={s.pageIcon}><Icon name="calendar" size={22}/></span><div><h1>发展日历</h1><p>公开事项与我的计划</p></div></div>
      <div className={s.headerActions}>
        <button type="button" className={s.iconButton} aria-label="刷新日程" disabled={pending} onClick={() => startRefresh(() => router.refresh())}><span className={pending ? s.spinning : ''}><Icon name="refresh" size={17}/></span></button>
        <Link className={s.addButton} href="/tracker"><Icon name="plus" size={16}/>新建计划</Link>
      </div>
    </header>

    <div className={s.toolbar}>
      <label className={s.search}><Icon name="search" size={18}/><input type="search" aria-label="搜索日程名称或关键词" placeholder="搜索日程名称、关键词" maxLength={100} value={query} onChange={e => {setQuery(e.target.value); setSelectedDay(null);}}/></label>
      <select aria-label="筛选发展方向" value={direction} onChange={e => {setDirection(e.target.value); setSelectedDay(null);}}><option value="">所有方向</option>{streams.map(path => <option key={path.code} value={path.code}>{path.name}</option>)}</select>
      <select aria-label="筛选日程状态" value={status} onChange={e => {setStatus(e.target.value); setSelectedDay(null);}}><option value="">所有状态</option>{['未开始', '进行中', '已结束', '未截止', '今日截止', '已截止', '今日待办', '已逾期', '已完成'].map(state => <option key={state}>{state}</option>)}</select>
      <button className={`${s.favoriteFilter} ${onlyFavorites ? s.filterActive : ''}`} type="button" aria-pressed={onlyFavorites} disabled={!data.userId || !favoritesReady} title={data.userId ? '收藏仅保存在当前账号的本浏览器中' : '登录后可查看收藏'} onClick={() => {setOnlyFavorites(!onlyFavorites); setSelectedDay(null);}}><Star filled={onlyFavorites}/>我的收藏</button>
    </div>

    {failed.length > 0 && <div className={s.notice} role="alert"><Icon name="refresh" size={15}/><span>{failed.join('、')}暂未加载{data.events.length ? '，已保留可用内容。' : '，请刷新重试。'}</span><button disabled={pending} onClick={() => startRefresh(() => router.refresh())}>{pending ? '刷新中…' : '重试'}</button></div>}
    {unauthorized && <div className={s.notice}><Icon name="shield" size={15}/><span>登录后可查看个人计划和收藏日程。</span><Link href="/login">去登录<Icon name="arrow" size={13}/></Link></div>}
    {data.invalidDates > 0 && <div className={s.notice}><span>{data.invalidDates} 条记录日期无效，暂未显示。</span><Link href="/data">查看信息中心</Link></div>}

    <div className={s.layout} aria-busy={pending}>
      <section className={s.monthPanel} aria-label="月历">
        <div className={s.monthToolbar}>
          <div className={s.monthNav}>
            <button type="button" className={`${s.iconButton} ${s.previous}`} aria-label="上个月" onClick={() => moveMonth(shiftMonth(month, -1))}><Icon name="chevron" size={18}/></button>
            <h2 aria-live="polite">{monthLabel(month)}</h2>
            <button type="button" className={s.iconButton} aria-label="下个月" onClick={() => moveMonth(shiftMonth(month, 1))}><Icon name="chevron" size={18}/></button>
            <button type="button" className={s.todayButton} onClick={() => moveMonth(data.today.slice(0, 7))}>今天</button>
          </div>
          <span className={s.monthCount}>{monthEvents.length} 项日程</span>
        </div>
        <div className={s.legend}><span><i className={s.greenDot}/>事项周期 / 开始</span><span><i className={s.goldDot}/>截止日期</span><span><i className={s.blueDot}/>个人计划</span></div>
        <div className={s.calendarScroll} ref={calendar}>
          <div className={s.calendar} aria-label={`${monthLabel(month)}日历，方向键切换日期`}>
            <div className={s.weekdays}>{weekdays.map(d => <span key={d}>{d}</span>)}</div>
            {weeks.map(week => {
              const segments = weekSegments(filtered, week);
              const visible = segments.filter(segment => segment.lane < MAX_LANES);
              return <div className={s.week} key={week[0]}>
                <div className={s.days}>{week.map((day, i) => <div key={day} className={`${s.dayCell} ${i > 4 ? s.weekend : ''} ${selectedDay === day ? s.selectedCell : ''}`}>
                  <button type="button" data-day={day} className={`${s.dayNumber} ${!day.startsWith(month) ? s.outside : ''} ${day === data.today ? s.isToday : ''}`} aria-label={`${day.replaceAll('-', '年').replace(/年(\d+)$/, '月$1日')}，${filtered.filter(e => overlaps(e, day)).length}项日程`} aria-current={day === data.today ? 'date' : undefined} aria-pressed={selectedDay === day} tabIndex={focusDay === day ? 0 : -1} onFocus={() => setFocusDay(day)} onClick={() => selectDay(day)} onKeyDown={e => dayKey(e, day)}>{Number(day.slice(8))}</button>
                </div>)}</div>
                <div className={s.eventLanes}>
                  {visible.map(segment => <button key={segment.event.id} type="button" data-event-id={segment.event.id} className={`${s.eventBar} ${s[segment.event.kind]} ${segment.continuesBefore ? s.continuedLeft : ''} ${segment.continuesAfter ? s.continuedRight : ''}`} style={{gridColumn: `${segment.from + 1} / ${segment.to + 2}`, gridRow: segment.lane + 1}} title={`${segment.event.title}\n${dateRange(segment.event)}`} onClick={() => openDetail(segment.event)}><span>{segment.event.title}</span>{segment.event.start !== segment.event.end && segment.to - segment.from >= 2 && <small>{segment.event.start.slice(5).replace('-', '.')} — {segment.event.end.slice(5).replace('-', '.')}</small>}</button>)}
                </div>
                <div className={s.moreRow}>{week.map(day => {const count = segments.filter(segment => segment.lane >= MAX_LANES && overlaps(segment.event, day)).length; return <div key={day}>{count > 0 && <button onClick={() => selectDay(day)} type="button" aria-label={`${day}还有${count}项日程`}>+{count} 项</button>}</div>;})}</div>
              </div>;
            })}
          </div>
        </div>
        {monthEvents.length === 0 && <div className={s.monthEmpty}>
          <Icon name="calendar" size={17}/><span>{filtered.length ? '本月暂无日程' : failed.length ? '暂时没有可显示的日程' : onlyFavorites && !favoriteIds.length ? '还没有收藏的日程' : hasFilters ? '没有符合筛选的日程' : '暂无已注明日期的日程'}</span>
          {filtered.length > 0 ? <button onClick={() => moveMonth(initialMonth(filtered, data.today))}>定位有日程的月份<Icon name="arrow" size={13}/></button> : hasFilters ? <button onClick={clearFilters}>清除筛选</button> : <Link href="/tracker">创建计划<Icon name="plus" size={13}/></Link>}
        </div>}
        <div className={s.calendarFooter}><span>北京时间 · 周一开始</span><Link href="/data">浏览信息中心<Icon name="arrow" size={13}/></Link></div>
      </section>

      <aside className={s.agenda} aria-label="日程列表">
        <section className={s.upcoming}>
          <div className={s.sectionHeading}><h2>{selectedDay ? `${Number(selectedDay.slice(5, 7))}月${Number(selectedDay.slice(8))}日` : '近期日程'}</h2>{selectedDay ? <button className={s.iconButton} aria-label="返回近期日程" onClick={() => setSelectedDay(null)}><Icon name="close" size={16}/></button> : <span className={s.muted}>接下来</span>}</div>
          <div className={s.upcomingList}>
            {sideEvents.length ? sideEvents.map(event => {
              const at = selectedDay || (event.start < data.today ? event.end : event.start);
              return <article className={s.upcomingItem} key={event.id}>
                <div className={s.eventDate}><b>{at.slice(5).replace('-', '.')}</b><small>{weekdays[(new Date(dayTime(at)).getUTCDay() + 6) % 7]}</small></div>
                <button type="button" className={s.upcomingTitle} onClick={() => openDetail(event)}><strong>{event.title}</strong><span><i className={event.kind === 'deadline' ? s.goldDot : event.kind === 'plan' ? s.blueDot : s.greenDot}/>{kindLabels[event.kind]}</span></button>
                {favoriteButton(event)}
              </article>;
            }) : <div className={s.agendaEmpty}><span className={s.emptyIcon}><Icon name="calendar" size={24}/></span><strong>{selectedDay ? '这一天暂无日程' : '暂无后续日程'}</strong><p>{hasFilters ? '试试调整筛选条件' : '为下一步留出时间'}</p>{hasFilters ? <button onClick={clearFilters}>清除筛选<Icon name="arrow" size={13}/></button> : <Link href="/tracker">安排我的计划<Icon name="arrow" size={13}/></Link>}</div>}
          </div>
        </section>
        <section className={s.allSection}>
          <div className={s.sectionHeading}><h2>全部日程</h2><span className={s.muted} aria-live="polite">{filtered.length} 项日程</span></div>
          <div className={s.listFilters}>
            <select aria-label="筛选年度" value={year} onChange={e => {setYear(e.target.value); setSelectedDay(null);}}><option value="">所有年度</option>{years.map(y => <option key={y} value={y}>{y}年</option>)}</select>
            <select aria-label="筛选日程类型" value={kind} onChange={e => {setKind(e.target.value); setSelectedDay(null);}}><option value="">所有类型</option>{Object.entries(kindLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
            <button type="button" disabled={!hasFilters} onClick={clearFilters}>清除</button>
          </div>
          <div className={s.allList}>
            {allEvents.map(event => <article className={s.listItem} key={event.id}>
              <div className={s.listItemHead}><button type="button" className={s.eventTitle} onClick={() => openDetail(event)}>{event.title}</button>{favoriteButton(event)}</div>
              <button type="button" className={s.dateLink} aria-label={`定位日程：${event.title}`} onClick={() => {moveMonth(event.start.slice(0, 7)); setSelectedDay(event.start);}}>{dateRange(event)}<Icon name="arrow" size={12}/></button>
              <div className={s.eventMeta}><span className={s.status}>{eventStatus(event, data.today)}</span><span>{event.paths.map(path => path.name).join(' / ') || kindLabels[event.kind]}</span></div>
            </article>)}
            {!allEvents.length && <div className={s.listEmpty}><Icon name="search" size={21}/><p>{failed.length ? '日程暂未加载' : onlyFavorites && !favoriteIds.length ? '还没有收藏的日程' : '没有符合条件的日程'}</p>{hasFilters && <button onClick={clearFilters}>清除筛选</button>}</div>}
          </div>
        </section>
      </aside>
    </div>

    <div className={s.toast} role="status" aria-live="polite">{pending ? '正在刷新日程…' : toast}</div>
    <dialog ref={dialog} className={s.dialog} aria-labelledby="calendar-detail-title" onClose={() => setDetail(null)} onClick={e => {if (e.target === e.currentTarget) dialog.current?.close();}}>
      {detail && <div className={s.dialogBody}>
        <div className={s.dialogTop}><span className={s.detailKind}><i className={detail.kind === 'deadline' ? s.goldDot : detail.kind === 'plan' ? s.blueDot : s.greenDot}/>{kindLabels[detail.kind]}</span><button type="button" className={s.iconButton} aria-label="关闭日程详情" autoFocus onClick={() => dialog.current?.close()}><Icon name="close" size={19}/></button></div>
        <h2 id="calendar-detail-title">{detail.title}</h2>
        <p className={s.detailDate}><Icon name="calendar" size={18}/>{dateRange(detail)}</p>
        <dl className={s.detailInfo}><div><dt>状态</dt><dd>{eventStatus(detail, data.today)}</dd></div><div><dt>方向</dt><dd>{detail.paths.map(p => p.name).join(' / ') || '未分类'}</dd></div><div><dt>来源</dt><dd>{detail.source}</dd></div>{detail.location && <div><dt>{/^\d{6}$/.test(detail.location) ? '区域编码' : '地点'}</dt><dd>{detail.location}</dd></div>}</dl>
        {detail.note && <p className={s.detailNote}>{detail.note}</p>}
        <div className={s.detailActions}><button className={s.detailSave} disabled={!data.userId || !favoritesReady} onClick={() => toggleFavorite(detail)}><Star filled={favoriteIds.includes(detail.id)}/>{favoriteIds.includes(detail.id) ? '已收藏' : '收藏日程'}</button>{safeOriginalUrl(detail.originalUrl) && <a href={safeOriginalUrl(detail.originalUrl)} target="_blank" rel="noopener noreferrer">官方原文<Icon name="link" size={14}/></a>}<Link className={s.addButton} href={detail.href}>{detail.kind === 'plan' ? '管理计划' : '查看事项'}<Icon name="arrow" size={14}/></Link></div>
        <small className={s.detailHint}>收藏仅保存在本浏览器，不会自动创建计划或通知。</small>
      </div>}
    </dialog>
  </div>;
}

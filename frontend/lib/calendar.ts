import type {Plan} from './api';

export type CalendarPath = {id?: number; code?: string | null; name: string};
export type TimelineEvent = {
  item_id: string; publication_id: string; title: string; at: string; label: string;
  paths?: CalendarPath[]; location?: string | null;
  description?: string;
  source?: {name?: string; publisher?: string};
  document?: {canonical_url?: string};
};
export type CalendarEvent = {
  id: string; title: string; start: string; end: string;
  kind: 'period' | 'start' | 'deadline' | 'plan';
  paths: CalendarPath[]; href: string; source: string; location: string;
  originalUrl?: string; planStatus?: Plan['status']; note?: string;
};
export type FeedState = 'ok' | 'error' | 'permission';
export type CalendarData = {
  events: CalendarEvent[]; today: string; userId: string | null; invalidDates: number;
  publicState: FeedState; planState: FeedState; pathsState: FeedState;
};
export const kindLabels: Record<CalendarEvent['kind'], string> = {
  period: '事项周期', start: '开始日期', deadline: '截止日期', plan: '个人计划',
};
const DAY = 86_400_000;
const dayFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
});

/** Date-only plans remain dates. Timestamped source records use Beijing time. */
export function calendarDay(value: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:$|T| )/.exec(value);
  if (!match) return null;
  const [, y, m, d] = match;
  const check = new Date(Date.UTC(+y, +m - 1, +d));
  if (check.getUTCFullYear() !== +y || check.getUTCMonth() !== +m - 1 || check.getUTCDate() !== +d) return null;
  if (value.length === 10) return value;
  const iso = value.replace(' ', 'T');
  const date = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + '+08:00');
  if (!Number.isFinite(date.getTime())) return null;
  const parts = dayFormatter.formatToParts(date);
  return ['year', 'month', 'day'].map(type => parts.find(p => p.type === type)!.value).join('-');
}
export function todayInShanghai() { return calendarDay(new Date().toISOString())!; }
export function dayTime(day: string) { return Date.parse(day + 'T00:00:00Z'); }
export function addDays(day: string, amount: number) { return new Date(dayTime(day) + amount * DAY).toISOString().slice(0, 10); }
export function shiftMonth(month: string, amount: number) {
  const [year, m] = month.split('-').map(Number);
  return new Date(Date.UTC(year, m - 1 + amount, 1)).toISOString().slice(0, 7);
}
export function monthBounds(month: string) { return {start: month + '-01', end: addDays(shiftMonth(month, 1) + '-01', -1)}; }
export function monthWeeks(month: string): string[][] {
  const {start, end} = monthBounds(month);
  const first = addDays(start, -(new Date(dayTime(start)).getUTCDay() + 6) % 7);
  const count = Math.ceil(((dayTime(end) - dayTime(first)) / DAY + 1) / 7);
  return Array.from({length: count}, (_, w) => Array.from({length: 7}, (_, d) => addDays(first, w * 7 + d)));
}
export function overlaps(event: CalendarEvent, start: string, end = start) { return event.start <= end && event.end >= start; }
export function initialMonth(events: CalendarEvent[], today: string): string {
  const month = today.slice(0, 7), bounds = monthBounds(month);
  if (events.some(e => overlaps(e, bounds.start, bounds.end))) return month;
  const dates = events.flatMap(e => [e.start, e.end]);
  dates.sort((a, b) => Math.abs(dayTime(a) - dayTime(today)) - Math.abs(dayTime(b) - dayTime(today)));
  return dates[0]?.slice(0, 7) || month;
}
export function eventStatus(event: CalendarEvent, today: string): string {
  if (event.planStatus === 'done') return '已完成';
  if (event.kind === 'deadline') return event.end < today ? '已截止' : event.end === today ? '今日截止' : '未截止';
  if (event.end < today) return event.kind === 'plan' ? '已逾期' : '已结束';
  if (event.start > today) return '未开始';
  return event.kind === 'plan' ? '今日待办' : '进行中';
}
export function dateRange(event: CalendarEvent) {
  const start = event.start.replaceAll('-', '.');
  return event.start === event.end ? start : start + ' — ' + event.end.replaceAll('-', '.');
}

export function normalizeCalendar(raw: TimelineEvent[], plans: Plan[], paths: CalendarPath[]) {
  const groups = new Map<string, {row: TimelineEvent; start?: string; end?: string}>();
  const events: CalendarEvent[] = [];
  let invalidDates = 0;
  for (const row of raw) {
    const day = calendarDay(row.at);
    if (!day) { invalidDates++; continue; }
    const id = 'public:' + row.publication_id + ':' + row.item_id;
    const group = groups.get(id) || {row};
    if (row.label === '开始') group.start = day;
    else group.end = day;
    groups.set(id, group);
  }
  for (const [id, {row, start, end}] of groups) {
    const base = {
      id, title: row.title, paths: row.paths || [], href: '/data/' + encodeURIComponent(row.publication_id),
      source: row.source?.name || row.source?.publisher || '公开事项', location: row.location || '',
      originalUrl: row.document?.canonical_url,
      note: row.description,
    };
    if (start && end && end < start) {
      // Retain inconsistent source endpoints as separate points, never invent a span.
      events.push({...base, id: id + ':start', start, end: start, kind: 'start'});
      events.push({...base, id: id + ':end', start: end, end, kind: 'deadline'});
      continue;
    }
    events.push({...base, start: start || end!, end: end || start!, kind: start && end ? 'period' : start ? 'start' : 'deadline'});
  }
  for (const plan of plans) {
    if (!plan.due_date) continue;
    const day = calendarDay(plan.due_date);
    if (!day) { invalidDates++; continue; }
    const path = paths.find(p => p.id === plan.path_id);
    events.push({id: 'plan:' + plan.id, title: plan.title, start: day, end: day, kind: 'plan',
      paths: path ? [path] : [], source: '我的计划', href: '/tracker', location: '', planStatus: plan.status, note: plan.note});
  }
  return {events: events.sort((a, b) => a.start.localeCompare(b.start) || a.id.localeCompare(b.id)), invalidDates};
}

export type WeekSegment = {event: CalendarEvent; from: number; to: number; lane: number; continuesBefore: boolean; continuesAfter: boolean};
/** Clip intervals per week and place each in the first non-overlapping lane. */
export function weekSegments(events: CalendarEvent[], week: string[]): WeekSegment[] {
  const lanes: number[] = [];
  return events.filter(e => overlaps(e, week[0], week[6]))
    .map(event => ({event, from: Math.max(0, Math.round((dayTime(event.start) - dayTime(week[0])) / DAY)),
      to: Math.min(6, Math.round((dayTime(event.end) - dayTime(week[0])) / DAY))}))
    .sort((a, b) => a.from - b.from || b.to - a.to || a.event.id.localeCompare(b.event.id))
    .map(segment => {
      let lane = lanes.findIndex(end => end < segment.from);
      if (lane < 0) lane = lanes.length;
      lanes[lane] = segment.to;
      return {...segment, lane, continuesBefore: segment.event.start < week[0], continuesAfter: segment.event.end > week[6]};
    });
}

import assert from 'node:assert/strict';
import test from 'node:test';
import {calendarDay, eventStatus, initialMonth, monthWeeks, normalizeCalendar, shiftMonth, weekSegments, type CalendarEvent, type TimelineEvent} from '../lib/calendar';

const event = (id: string, start: string, end = start): CalendarEvent => ({id, start, end, title: '同名事项', kind: 'period', paths: [], source: 'test', location: '', href: '/data/test'});
test('Beijing dates, invalid dates and date-only plans', () => {
  assert.equal(calendarDay('2026-11-07'), '2026-11-07');
  assert.equal(calendarDay('2026-11-07T18:00:00Z'), '2026-11-08');
  assert.equal(calendarDay('2026-11-07T23:59:00'), '2026-11-07');
  assert.equal(calendarDay('2025-02-29'), null);
  assert.equal(calendarDay('2026-02-30T12:00:00Z'), null);
  assert.equal(calendarDay('not a date'), null);
  assert.equal(calendarDay('2026-11-25T15:59:59+00:00'), '2026-11-25');
  assert.equal(calendarDay('2026-11-25T22:00:00+00:00'), '2026-11-26');
  assert.equal(calendarDay('2026-11-29T09:00:00+00:00'), '2026-11-29');
});
test('Monday-first weeks, leap years and year boundaries', () => {
  assert.equal(shiftMonth('2026-12', 1), '2027-01');
  assert.equal(shiftMonth('2026-01', -1), '2025-12');
  assert.equal(monthWeeks('2026-11')[0][0], '2026-10-26');
  assert.equal(monthWeeks('2024-02').flat().includes('2024-02-29'), true);
  assert.equal(monthWeeks('2026-02').length, 5);
  assert.equal(monthWeeks('2021-02').length, 4);
});
test('Start and deadline grouping never merges distinct publications or plans with the same title', () => {
  const row = (publication: string, label: string, at: string): TimelineEvent => ({publication_id: publication, item_id: '1', title: '同名事项', label, at, paths: [{code: 'employment', name: '实习就业'}]});
  const normalized = normalizeCalendar([
    row('a', '开始', '2026-11-01'), row('a', '截止/失效', '2026-11-10'), row('b', '截止/失效', '2026-11-10'), row('c', '开始', 'bad'),
  ], [{id: 1, title: '同名事项', user_id: 'u', due_date: '2026-11-10', path_id: null, status: 'done', note: '', created_at: '', updated_at: ''}], []);
  assert.equal(normalized.events.length, 3);
  assert.equal(normalized.invalidDates, 1);
  assert.equal(normalized.events[0].end, '2026-11-10');
  assert.equal(normalized.events[0].kind, 'period');
  assert.equal(normalized.events.find(e => e.id === 'plan:1')?.planStatus, 'done');
});
test('Reversed source endpoints remain points, not a fabricated range', () => {
  const base = {publication_id: 'a', item_id: 'b', title: 'test'};
  const {events} = normalizeCalendar([{...base, at: '2026-11-10', label: '开始'}, {...base, at: '2026-11-01', label: '截止/失效'}], [], []);
  assert.equal(events.length, 2);
  assert.ok(events.every(e => e.start === e.end));
});
test('Cross-week intervals are clipped; occupied lanes do not overlap', () => {
  const week = monthWeeks('2026-11')[0];
  const segments = weekSegments([event('a', '2026-10-20', '2026-11-09'), event('b', '2026-10-27', '2026-10-29'), event('c', '2026-10-30', '2026-11-01')], week);
  assert.equal(segments[0].from, 0); assert.equal(segments[0].to, 6);
  assert.equal(segments[0].continuesBefore, true); assert.equal(segments[0].continuesAfter, true);
  assert.equal(segments[1].lane, 1); assert.equal(segments[2].lane, 1);
  for (const a of segments) for (const b of segments) if (a !== b && a.lane === b.lane) assert.ok(a.to < b.from || b.to < a.from);
});
test('Select closest available month without faking new records', () => {
  assert.equal(initialMonth([event('a', '2026-10-21'), event('b', '2026-03-01')], '2026-11-07'), '2026-10');
  assert.equal(initialMonth([], '2026-11-07'), '2026-11');
  assert.equal(initialMonth([event('a', '2026-10-01', '2026-12-01')], '2026-11-07'), '2026-11');
});
test('Statuses distinguish dates, overdue and completed plans', () => {
  assert.equal(eventStatus(event('a', '2026-11-01', '2026-11-10'), '2026-11-07'), '进行中');
  assert.equal(eventStatus({...event('a', '2026-11-25'), kind: 'deadline'}, '2026-11-07'), '未截止');
  assert.equal(eventStatus({...event('a', '2026-11-25'), kind: 'deadline'}, '2026-11-25'), '今日截止');
  assert.equal(eventStatus({...event('a', '2026-11-25'), kind: 'deadline'}, '2026-11-26'), '已截止');
  assert.equal(eventStatus({...event('a', '2026-11-01'), kind: 'plan', planStatus: 'todo'}, '2026-11-07'), '已逾期');
  assert.equal(eventStatus({...event('a', '2026-11-01'), kind: 'plan', planStatus: 'done'}, '2026-11-07'), '已完成');
});

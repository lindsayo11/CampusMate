import {cookies} from 'next/headers';
import {DevelopmentCalendar} from '@/components/development-calendar';
import {normalizeCalendar, todayInShanghai, type CalendarPath, type FeedState, type TimelineEvent} from '@/lib/calendar';
import type {Plan} from '@/lib/api';
import {optionalWorkspaceApi} from '@/lib/workspace';

export const metadata = {title: '发展日历 · CampusMate 校伴'};

export default async function DataTimeline() {
  const token = (await cookies()).get('cm_access')?.value;
  async function feed<T>(path: string): Promise<{state: FeedState; rows: T[]}> {
    try {
      const response = await fetch((process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000') + path, {
        cache: 'no-store', signal: AbortSignal.timeout(10000), headers: token ? {Authorization: `Bearer ${token}`} : {},
      });
      if (response.status === 401 || response.status === 403) return {state: 'permission', rows: []};
      if (!response.ok) return {state: 'error', rows: []};
      const rows: unknown = await response.json();
      return Array.isArray(rows) ? {state: 'ok', rows} : {state: 'error', rows: []};
    } catch { return {state: 'error', rows: []}; }
  }
  const [timeline, plans, paths, account] = await Promise.all([
    feed<TimelineEvent>('/v1/data/timeline'), feed<Plan>('/v1/plans'),
    feed<CalendarPath>('/v1/paths'), optionalWorkspaceApi('/v1/account'),
  ]);
  return <DevelopmentCalendar data={{...normalizeCalendar(timeline.rows, plans.rows, paths.rows),
    today: todayInShanghai(), userId: account?.user_id || null,
    publicState: timeline.state, planState: plans.state, pathsState: paths.state,
  }}/>;
}

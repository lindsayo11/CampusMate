import s from '@/components/development-calendar.module.css';

export default function CalendarLoading() {
  return <div className={s.page} aria-busy="true" aria-label="正在加载日历">
    <div role="status" className={s.pageHeader}><h1>发展日历</h1><span className={s.muted}>正在加载日程…</span></div>
    <div aria-hidden="true"><div className={s.skeletonLine} style={{height: 43, marginBottom: 30}}/>
      <div className={s.layout}><div><div className={s.skeletonTitle} style={{marginBottom: 28}}/><div className={s.skeletonGrid}/></div>
        <div className={s.agenda}><div className={s.skeletonTitle}/>{Array.from({length: 9}, (_, i) => <div key={i} className={s.skeletonLine} style={{width: i % 3 ? '100%' : '65%', marginBottom: 30}}/>)}</div>
      </div>
    </div>
  </div>;
}

import Link from 'next/link';
import {pageNumbers} from '@/lib/pagination';
import {Icon} from './ui';
import styles from './pagination.module.css';

export function Pagination({total,limit,offset,href,label}:{total:number;limit:number;offset:number;href:(offset:number)=>string;label:string}){
  const pages=Math.ceil(total/limit),current=Math.floor(offset/limit)+1;
  if(pages<1)return null;
  return <nav className={styles.pagination} aria-label={label}>
    {current>1?<Link className={styles.page} aria-label="上一页" rel="prev" href={href(Math.max(0,offset-limit))}><span className={styles.previous}><Icon name="chevron" size={20}/></span></Link>:<button className={styles.page} type="button" aria-label="上一页" disabled><span className={styles.previous}><Icon name="chevron" size={20}/></span></button>}
    {pageNumbers(current,pages).map((page,i)=>page==='ellipsis'?<span key={'gap-'+i} className={styles.ellipsis} aria-hidden="true">…</span>:<Link key={page} className={styles.page} href={href((page-1)*limit)} aria-label={'第 '+page+' 页'} aria-current={current===page?'page':undefined}>{page}</Link>)}
    {current<pages?<Link className={styles.page} aria-label="下一页" rel="next" href={href(offset+limit)}><Icon name="chevron" size={20}/></Link>:<button className={styles.page} type="button" aria-label="下一页" disabled><Icon name="chevron" size={20}/></button>}
  </nav>;
}

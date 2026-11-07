import Link from "next/link";
import type { Opportunity } from "@/lib/api";
import {NoticeArtwork} from "./notice-artwork";
import {noticeDate} from "@/lib/explore";
import {Icon} from "./ui";
import styles from "./explore.module.css";
const labels: Record<string,string> = {job:"就业",contest:"竞赛",civil_service:"考公",volunteer:"志愿",club:"社团",graduate:"升学"};
export function OpportunityCard({item}:{item:Opportunity}) {
 const pathCode=({job:'employment',civil_service:'national_civil_service',graduate:'recommendation_exemption'} as Record<string,string>)[item.type];
 const paths=pathCode?[{code:pathCode}]:[];
 const deadline=item.deadline?new Date(item.deadline).getTime():NaN;
 const expired=Number.isFinite(deadline)&&deadline<Date.now();
 return <article className={styles.noticeCard}>
  <Link href={'/opportunity/'+item.id} aria-label={'查看机会：'+item.title}><NoticeArtwork title={item.title} paths={paths} seedKey={'opportunity-'+item.id}/></Link>
  <div className={styles.cardBody}><span className={styles.category}>{labels[item.type]||item.type} · {item.location||'校园机会'}</span>
   <h3><Link href={'/opportunity/'+item.id}>{item.title}</Link></h3><p className={styles.summary}>{item.summary}</p>
   <span className={styles.status} data-state={expired?'expired':Number.isFinite(deadline)?'open':'needs_confirmation'}>{Number.isFinite(deadline)?(expired?'已截止 · ':'截止 ')+noticeDate(item.deadline):'报名时间待核验'}</span>
   <footer><small title={item.organization}>{item.organization}</small><Link href={'/opportunity/'+item.id}>查看详情<Icon name="arrow" size={14}/></Link></footer>
  </div>
 </article>;
}


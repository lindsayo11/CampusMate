import {notFound} from 'next/navigation';
import Link from 'next/link';
import {NoticeDetail} from '@/components/notice-detail';
import {channelHref,getChannel} from '@/lib/development-channels';
import type {Publication} from '@/lib/explore';
import styles from '@/components/explore.module.css';
export default async function DataDetail({params,searchParams}:{params:Promise<{id:string}>;searchParams:Promise<{item?:string;channel?:string}>}){
  const {id}=await params,p=await searchParams,item=p.item,channel=getChannel(p.channel);
  const response=await fetch((process.env.API_INTERNAL_URL||'http://127.0.0.1:8000')+'/v1/data/publications/'+encodeURIComponent(id),{cache:'no-store',signal:AbortSignal.timeout(15000)});
  if(response.status===404)notFound();
  if(!response.ok)throw Error('公告暂时无法读取');
  const data=await response.json() as Publication;
  if(item&&!data.items.some((i:{id:string})=>i.id===item))notFound();
  return <div className={styles.surface}><header className={styles.heading}><h1>{channel?channel.name+' · 公告详情':'公告详情'}</h1><Link href={channelHref(channel?.code)}>← 返回{channel?.name||'信息中心'}</Link></header><NoticeDetail data={data} itemId={item} channel={channel?.code}/></div>;
}

"use client";
import {useState} from 'react';
import Link from 'next/link';
import type {CatalogItem} from '@/lib/catalog';
import {availabilityLabels,noticeDate,noticeSummary} from '@/lib/explore';
import {getChannel,noticeHref,type ChannelCode} from '@/lib/development-channels';
import {NoticeArtwork} from './notice-artwork';
import {NoticeDialog} from './notice-detail';
import {Icon} from './ui';
import styles from './explore.module.css';

export function NoticeGrid({items,channel}:{items:CatalogItem[];channel?:ChannelCode}){
  const [selected,setSelected]=useState<CatalogItem|null>(null);
  return <><div className={styles.grid}>{items.map(item=><article className={styles.noticeCard} key={item.id}>
    <button className={styles.coverButton} onClick={()=>setSelected(item)} aria-label={'查看公告：'+item.title}><NoticeArtwork paths={item.paths} title={item.title} seedKey={item.id}/></button>
    <div className={styles.cardBody}><div className={styles.category}>{getChannel(channel)?.name||item.paths[0]?.name||'公开信息'}<span> · </span>{item.content_kind==='news_report'?'活动报道':item.content_kind==='reference'?'政策参考':'通知公告'}</div>
      <h3><Link href={noticeHref(item.publication_id,item.id,channel)} onClick={e=>{if(!e.metaKey&&!e.ctrlKey&&!e.shiftKey){e.preventDefault();setSelected(item)}}}>{item.title}</Link></h3>
      <p className={styles.summary}>{noticeSummary(item)}</p><span className={styles.status} data-state={item.availability}>{availabilityLabels[item.availability||'']||'请核对原文'}{item.deadline?' · '+noticeDate(item.deadline):''}</span>
      <footer><small title={item.source.name}>{item.source.name}</small><button type="button" onClick={()=>setSelected(item)}>查看详情<Icon name="arrow" size={15}/></button></footer>
    </div></article>)}</div>{selected&&<NoticeDialog publicationId={selected.publication_id} itemId={selected.id} channel={channel} onClose={()=>setSelected(null)}/>}</>;
}

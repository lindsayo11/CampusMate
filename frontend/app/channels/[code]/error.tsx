"use client";

import Link from 'next/link';
import {useParams} from 'next/navigation';
import {useTransition} from 'react';
import {getChannel} from '@/lib/development-channels';
import {Icon} from '@/components/ui';
import styles from '@/components/explore.module.css';

export default function ChannelError({retry}:{retry:()=>void}){
  const params=useParams<{code:string}>();
  const channel=getChannel(params.code);
  const [pending,startTransition]=useTransition();
  return <div className={styles.surface}>
    <header className={styles.heading}><div><h1>{channel?.name||'发展频道'}</h1><p>{channel?.description}</p></div></header>
    <section className={styles.empty} role="alert">
      <h2>频道信息暂时无法读取</h2><p>可以重试，筛选条件会保留。</p>
      <button className={styles.primary} onClick={()=>startTransition(retry)} disabled={pending}><Icon name="refresh" size={16}/>{pending?'正在重试…':'重新加载'}</button>
      <Link className={styles.secondary} href="/login">重新登录</Link>
    </section>
  </div>;
}

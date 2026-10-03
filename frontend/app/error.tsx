"use client";
import Link from 'next/link';
import {Icon} from '@/components/ui';
export default function ErrorPage({reset}:{reset:()=>void}){return <div className="error-page"><span className="empty-icon"><Icon name="link" size={28}/></span><h1>暂时无法打开此页面</h1><p>服务连接可能中断，或当前登录状态已失效。可以重试，或重新登录。</p><div className="button-row" style={{justifyContent:'center'}}><button className="primary" onClick={reset}>重新加载</button><Link className="button secondary" href="/login">前往登录</Link><Link className="button quiet" href="/">返回工作台</Link></div></div>}

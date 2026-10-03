import Link from 'next/link';
import {Icon} from '@/components/ui';
export default function NotFound(){return <div className="error-page"><span className="empty-icon"><Icon name="search" size={28}/></span><p className="eyebrow">404 · PAGE NOT FOUND</p><h1>页面或机会不存在</h1><p>内容可能已经下线，或当前入口尚未开放。</p><Link className="button primary" href="/data">返回信息中心<Icon name="arrow" size={14}/></Link></div>}

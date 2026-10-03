import {privateApi} from '@/lib/session-api';
import Link from 'next/link';
import {Icon} from '@/components/ui';
export default async function AdminLayout({children}:{children:React.ReactNode}){
 const account=await privateApi('/v1/account');
 if(!account.is_admin)return <div className="error-page"><span className="empty-icon"><Icon name="shield" size={30}/></span><h1>需要管理员权限</h1><p>当前账号可以使用学生功能。数据导入、审核和平台管理仅向管理员开放。</p><Link className="button primary" href="/">返回学生工作台</Link></div>;
 return <><div className="admin-banner"><b><Icon name="shield" size={14}/>管理员工作空间</b><span>平台内容管理 · 与个人计划分开</span><Link href="/">切回学生视图 →</Link></div>{children}</>
}

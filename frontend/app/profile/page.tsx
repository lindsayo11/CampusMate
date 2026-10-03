import Link from 'next/link';
import {privateApi} from '@/lib/session-api';
import {ProfileForm} from '@/components/profile-form';
import {PageHeading,Icon} from '@/components/ui';
export default async function ProfilePage(){const [profile,account]=await Promise.all([privateApi('/v1/profile'),privateApi('/v1/account')]);return <div className="shell"><PageHeading eyebrow="MY PROFILE" title="个人资料与发展目标" description="由你决定填写哪些信息，用于发展规划、条件核对和同校技能匹配。"/><div className="settings-layout"><ProfileForm initial={profile}/><aside className="settings-note"><section className="rail-tip"><Icon name="shield" size={23}/><h3>当前身份：{account.is_admin?'管理员':'普通用户'}</h3><p>{account.is_admin?'你可以使用学生功能，并进入独立运营后台管理平台内容。切换界面不会切换登录账号。':'你可以管理自己的画像、计划、提醒和会话。平台数据发布与删除由管理员管理。'}</p>{account.is_admin&&<Link href="/admin">进入运营后台 →</Link>}</section><h3>个人信息由你掌握</h3><p>开启技能展示后，同校同学才能通过匹配找到你。资格核对仅使用已支持、已核验的规则，资料不完整时会提示信息不足。</p><Link href="/safety">隐私与安全设置 →</Link></aside></div></div>}

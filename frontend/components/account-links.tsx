import Link from "next/link";
import {cookies} from "next/headers";
export async function AccountLinks(){
 let admin=false;try{const token=(await cookies()).get("cm_access")?.value;const r=await fetch((process.env.API_INTERNAL_URL||"http://127.0.0.1:8000")+"/v1/account",{cache:"no-store",signal:AbortSignal.timeout(3000),headers:token?{Authorization:`Bearer ${token}`}:{}});if(r.ok)admin=(await r.json()).is_admin===true}catch{}
 return <nav style={{display:"flex",gap:20,padding:16,flexWrap:"wrap"}} aria-label="账户与行动"><Link href="/login">登录 / 退出</Link><Link href="/profile">个人资料</Link><Link href="/notifications">通知中心</Link><Link href="/team-manager">团队管理</Link><Link href="/safety">隐私与安全</Link>{admin&&<Link href="/admin">运营后台</Link>}</nav>
}

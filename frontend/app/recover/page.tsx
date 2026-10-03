export const dynamic = "force-dynamic";
import Form from "@/components/recover-form";
export default function Page() {
 const configured = process.env.SUPABASE_URL?.startsWith("https://") && !!process.env.SUPABASE_ANON_KEY;
 if (!configured) return <div className="shell narrow"><h1>身份服务尚未配置</h1><p>登录、注册和找回密码需要配置 Supabase。演示模式使用内置身份，无需登录。</p><a href="/">返回首页</a></div>;
 return <Form/>;
}

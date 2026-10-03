# 邮箱密码找回部署与验收

代码入口：/recover；登录页面包含“忘记密码”链接。服务端 /api/session/recovery 的 POST 请求验证码，PATCH 验证 recovery OTP 后修改密码。

## 配置
沿用 Web SUPABASE_URL、SUPABASE_ANON_KEY、APP_ORIGIN，不需要 service-role key。
在 Supabase Authentication → Email Templates → Reset Password 中安装 supabase/templates/recovery.html，使用 {{ .Token }} 显示验证码。默认链接型邮件模板不适用于本页面，必须完成此配置后再开放找回入口。
配置自己的 SMTP、OTP 到期时间和身份服务速率限制。当前请求不接收 CAPTCHA token；如果 Supabase 开启 CAPTCHA，需要先接入验证码组件及 captcha_token 转发，不能绕过服务商校验。生产运营需同时配置代理层请求频控。

## 边界
邮箱存在与否返回相同提示；429 与上游 5xx 分别提示频控或服务不可用。修改密码只使用本次验证返回的 recovery session，不使用浏览器里可能存在的其他用户会话。
验证码与密码不写日志，不放 URL/localStorage，恢复会话不返回前端或设置登录 cookie。
密码修改后请求全局注销并清除本机登录 cookie。全局注销失败时明确告知，不把修改密码说成失败。已经签发的 access JWT 可能在到期前仍然有效；实际撤销效果需结合 Auth 配置验收，不承诺所有设备即时退出。
OTP 被消费后若密码更新失败，需要重新获取 OTP；若请求超时结果不明，先尝试新密码登录。

## 真实服务验收（尚未执行）
1. 使用正式测试邮箱接收验证码，输入错误码/过期码应拒绝，正确码可重设。
2. 同一码第二次提交应失败；新密码可登录、旧密码不可登录。
3. 浏览器已登录其他账号时，找回只修改目标邮箱账号；完成后清除当前浏览器会话。
4. 验证邮件发送频控、OTP 尝试频控、SMTP 失败、身份服务不可用。
5. 多设备登录后重设，检查 refresh session 撤销；记录旧 access token 的有效期边界。

## 自动测试
7 项新增恢复协议测试，加原有 8 项身份测试，共 15 项通过。使用模拟 Supabase HTTP 响应，不能代替真实认证/SMTP 联调。

官方协议参考（2026-09-28 核对）：
- https://supabase.com/docs/guides/auth/auth-email-templates
- https://supabase.com/docs/reference/javascript/auth-verifyotp
- https://supabase.com/docs/reference/javascript/auth-updateuser
- https://github.com/supabase/auth/blob/master/openapi.yaml

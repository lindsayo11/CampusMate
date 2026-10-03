# Email Signup OTP

在 Supabase Dashboard 中打开 Authentication → Email Templates → Confirm signup，替换为 `supabase/templates/confirmation.html`。模板必须渲染 `{{ .Token }}`；注册页会把这 6 位验证码提交到 `/api/session`，由 Supabase Auth 验证后再设置账号密码。

保持 Confirm email 开启。当前项目的 `GET /auth/v1/settings` 已确认邮箱注册开启且未自动确认，但这只能说明身份服务接受了请求，不能证明邮件已经投递。

不要依赖 Supabase 默认 SMTP：它只向项目组织成员地址发送，当前限制为每小时约 2 封，且没有投递 SLA。外部收件地址必须在 Authentication → SMTP 中配置自有 SMTP，并填写发件人、SMTP 主机、端口、用户名和密码；同时在邮件服务商验证发件域名的 SPF/DKIM。SMTP 密码必须是服务商创建时返回的完整密钥，而不是密钥名称。保存后先用正式测试邮箱验证邮件正文包含数字验证码，再开放注册。

如果日志出现 `/auth/v1/verify` 的 403，它表示提交的验证码无效、已过期或邮件从未到达，不代表发送成功。排查同一时间的 `/auth/v1/signup`、`/auth/v1/resend` 状态，并检查 QQ 垃圾箱、黑名单和 SMTP 投递日志。

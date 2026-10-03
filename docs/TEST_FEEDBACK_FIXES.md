# 测试反馈修复与复测报告

日期：2026-09-29（UTC）。基于 v0.23.0-preview.1，保持原有版本标识，本包为测试反馈修订版，不是正式发布验收版。

## 修改内容

1. 开发脚本设置 APP_ORIGIN，默认 http://127.0.0.1:3000，随 PORT 变化；远程域名通过环境变量显式指定。保留严格来源比较，不信任 Host 或转发头。
2. 后端代理的来源/路径拒绝改成 JSON detail，消除前端解析纯文本导致的 SyntaxError。
3. 演示 API 启动输出明显警告，说明 x-user-id 可模拟管理员；保留多账号演示功能，仍禁止公开部署。
4. 新增开发进程管理器：每个服务最多重启三次，耗尽后终止整组，SIGINT/SIGTERM 清理子进程组。无法抵御整个主机退出。
5. 安全页首屏加载提示，成功返回后才显示空记录，失败支持重试；通知页增加服务端加载界面。
6. 看板表单增加统一控件样式、间距、焦点和小屏适配。
7. 未配置 Supabase 时，登录/找回页提前说明原因和演示免登录入口；配置后保留原表单。服务端按请求读取配置，不暴露密钥。
8. 额外修复机会列表在浏览器端构造相对 URL 的异常；列表辅助函数读取失败不再伪装成空列表。
9. 开发依赖安装遵循已有 requirements-tested.txt；增加来源、进程管理测试和真实代理写入冒烟检查。

## 实际测试

| 检查 | 结果 |
| --- | --- |
| 后端既有业务/权限/迁移测试 | 52 passed，1 个 Starlette 测试客户端弃用警告 |
| 前端身份协议、范围与来源测试 | 19 passed（原 16 项 + 新 3 项） |
| 开发进程管理故障注入 | 2 passed；重启预算、整组停止和中断清理 |
| TypeScript | 通过 |
| Next.js production build | 通过，使用项目已有 restricted-node.cjs 环境兼容脚本 |
| API/Web/Worker 冷启动 | 通过；18 个主体页面 HTTP 200 |
| 真实代理 POST | 正确来源保存看板成功；恶意来源 403 且 JSON 可解析 |
| Worker/备份恢复 | 到期提醒仅投递一次；29 张表恢复后行数一致 |
| Shell 语法 | dev.sh 通过 |
| 浏览器桌面/Pixel 7 套件 | 未完成：Chromium 启动 SIGTRAP；首项启动失败后停止，其余 21 项未运行 |

首次直接执行 pytest 未先迁移数据库，触发预期的 schema 门禁；改用项目 check.sh 的隔离数据库和迁移流程后 52 项通过。首次依赖下载哈希不匹配，未关闭校验，禁用下载缓存重新安装后成功。首次普通构建因当前环境缺少 uv_resident_set_memory 所需系统信息失败，使用项目原有兼容脚本后完成。

## 剩余边界

- 浏览器真实点击、桌面/手机布局尚未验收，尤其新增加载态与表单样式需要在正常 Chromium 环境复验。
- 真实 Supabase 邮件/登录、PostgreSQL、Docker/TLS 不在此次验收范围；协议受控测试不能替代外部服务。
- 演示模式的任意身份切换仍是显式便利功能，日志警告不等同于访问控制。
- 不存在的机会页返回 not-found 内容，但当前流式页面 HTTP 状态可能为 200（既有行为），若用于公开 SEO 或严格监控需后续处理。
- 没有发现此次已通过测试覆盖范围内的新业务回归；不能据此保证所有场景无问题。

## 复现

```bash
export DEMO_MODE=true ADMIN_USER_IDS=demo-user
bash scripts/dev.sh
# 浏览器访问 http://127.0.0.1:3000
# 远程环境启动前显式 export APP_ORIGIN=https://实际域名
```

```bash
bash scripts/check.sh
backend/.venv/bin/python scripts/runtime_smoke.py
backend/.venv/bin/python scripts/e2e.py
```

受限环境如遇 uv_resident_set_memory，可按 README 设置 NODE_OPTIONS；正常主机无需设置。测试日志摘要保存在 docs/feedback-test-evidence/。源码修订补丁位于 docs/feedback-fixes.patch。

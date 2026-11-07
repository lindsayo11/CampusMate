# 本地动效预览

此改动仅针对当前本地检出；未连接或修改 VPS，也未替换其他目录的项目。

## 启动

在项目根目录运行：

```powershell
& .\backend\.venv\Scripts\python.exe .\scripts\preview_motion.py
```

工作台：<http://127.0.0.1:3000/console>  
公开首页：<http://127.0.0.1:3000/home>

端口被占用时脚本会退出，不会强制终止其他服务。可通过
`--api-port 8002 --web-port 3001` 指定其他端口。脚本监听回环地址，
使用 `local-data/demo.db`，不覆盖已有环境文件；关闭采集器及云端模型调用。
未创建本地数据库时，使用仓库自带的公开快照初始化。它不是 VPS 的实时数据。

如需预览生产构建（在 frontend 目录执行前两条命令）：

```powershell
node node_modules/typescript/bin/tsc --noEmit
node node_modules/next/dist/bin/next build
```

然后回到根目录运行：

```powershell
& .\backend\.venv\Scripts\python.exe .\scripts\preview_motion.py --production
```

使用 Node 直接启动检查与构建，避开 Windows 的 npm 命令脚本对目录名中 `&` 的解析问题。

## 改动范围

- 工作台分组入场、真实统计值递增、卡片及按钮交互反馈。
- 主导航选中标记、各栏目入场、设置和创新创业步骤切换动效。
- 四个公开页面滚动入场；首页轨道响应指针、阅读进度、可暂停的信息轮播。
- 工作台顶部与首页右下角提供动效开关，同源页面之间同步偏好。
- 遵循系统减少动态效果设置；低性能设备降级；公开页离屏/后台轮播暂停。
- 动画只增强已渲染的内容，不依靠动画完成来显示内容，不改动业务数据接口。

主要实现：`frontend/components/workspace-motion.tsx`、
`frontend/lib/motion-tokens.ts`、`frontend/app/motion.css`、
`frontend/public/landing/motion.js` 和同目录 `motion.css`。

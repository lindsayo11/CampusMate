# 环境说明

源码不包含已安装依赖、虚拟环境、测试数据库或浏览器二进制，按 [README](README.md) 的命令安装即可。

## 版本要求

| 组件 | 版本 |
|---|---|
| Python | 3.12 或以上（3.11 起支持，验收使用 3.12 / 3.13） |
| Node.js | 22 或以上 |
| 数据库 | SQLite（默认）或 PostgreSQL 16 |

根目录 `.env.example` 与 [frontend/.env.example](frontend/.env.example) 列出全部配置项，示例中不含任何真实凭据。

## 本地演示（无 Docker）

在仓库根目录：

```bash
export DEMO_MODE=true
export ADMIN_USER_IDS=demo-user
bash scripts/dev.sh
```

脚本会创建后端独立虚拟环境、安装前端锁定依赖，并启动 API、Worker、Web。三个服务只监听回环地址，退出脚本时一并停止。安装阶段需要能访问包源。

也可以直接用启动器，它会额外准备演示快照与环境文件：

```bash
backend/.venv/bin/python scripts/start_local.py
```

**演示模式不要用于公开部署。** 该模式下 `x-user-id` 请求头直接决定身份，包括管理员身份。

## 外部身份服务

配置 `SUPABASE_URL`、`SUPABASE_ANON_KEY`、`ADMIN_USER_IDS`，并把 `DEMO_MODE` 置为 `false`；前端需要同样的 Supabase 配置。

支持邮箱注册 / 确认后登录与自动续期，需要真实的 Supabase 项目和邮件服务才能联调。不要提交 `.env`。

## 环境自检与验证

```bash
# 只输出某项配置是否已设置，不打印密钥内容
python scripts/doctor.py

# 使用独立临时数据库运行测试、类型检查与生产构建
bash scripts/check.sh
```

## Docker

在装有 Docker Engine 与 Compose 的 Linux 主机上：

```bash
docker compose up --build
```

生产编排还需要 `.env` 中的 `POSTGRES_PASSWORD`、`APP_ORIGIN`、`ADMIN_USER_IDS` 等，细节见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

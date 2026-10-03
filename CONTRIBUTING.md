# 贡献指南

感谢愿意参与 CampusMate。提交前请先看这一页。

## 环境准备

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -c backend/requirements-tested.txt -e './backend[dev]'

cd frontend && npm ci && npm run build && cd ..

backend/.venv/bin/python scripts/start_local.py --collector-off
```

Windows 将 `backend/.venv/bin/python` 换成 `backend/.venv/Scripts/python.exe`。

## 提交前必须通过

```bash
bash scripts/check.sh
```

它会依次运行后端测试、前端测试、TypeScript 类型检查和生产构建。改动涉及页面交互时，另外跑一遍浏览器测试：

```bash
cd frontend && npx playwright install --with-deps chromium
cd .. && backend/.venv/bin/python scripts/e2e.py
```

CI 会执行同样的检查，本地先跑通可以省一轮来回。

## 代码约定

- **后端**：Python 3.12+，`ruff` 行宽 100。新增数据库结构必须写 Alembic 迁移，放在 `backend/migrations/versions/`，并保证 `alembic check` 无差异。
- **前端**：Next.js App Router + TypeScript，不引入 UI 框架依赖。页面文本使用中文，保持与现有页面一致的措辞风格。
- **测试**：新增业务分支请补测试。后端放 `backend/tests/`，前端单元测试放 `frontend/tests/`，浏览器流程放 `frontend/e2e/`。
- **接口契约**：改动 API 时同步更新 `specs/openapi.json` 和对应的 JSON Schema。
- **文档**：面向使用者的行为变化，更新 `README.md` 或 `docs/` 下相应文档。

## 数据与采集的硬性红线

本项目处理的是公开信息，采集部分有几条不能松动的约束。贡献相关代码时请遵守：

1. **不绕过来源治理**。采集只访问已登记且通过校准的官方主机，保持 HTTPS 白名单、robots 检查、逐跳重定向复核和体积/频率限制。
2. **不提交真实用户数据**。演示数据必须是公开信息或明确标记的合成数据；个人相关表在导出快照时必须清空。
3. **不提交密钥**。凭据一律走环境变量。`.env` 已在 `.gitignore` 中，不要用 `git add -f` 强行加入。
4. **不虚构事实**。系统不得编造市场规模、收入、履历、法规要求或资格结论；信息不足时显示"未收录"，而不是猜一个答案。
5. **不破坏"先确认后写入"**。Agent 与采集链路中的写操作必须保留人工确认环节。

## 提交流程

1. Fork 仓库并从 `main` 拉出分支，分支名用 `feat/…`、`fix/…`、`docs/…` 之类的前缀。
2. 一个 PR 只做一件事，标题写清改了什么以及为什么。
3. PR 描述里附上验证方式：跑了哪些测试、结果如何。涉及界面变化的请附截图。
4. 确认 CI 通过后等待审核。

## 报告问题

提 Issue 时请说明：复现步骤、期望结果、实际结果，以及运行环境（操作系统、Python / Node 版本、数据库类型）。涉及采集或解析失败的问题，请附上来源 URL 与错误输出（注意不要带密钥）。

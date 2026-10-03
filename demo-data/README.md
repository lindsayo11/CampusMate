# 演示数据

本目录存放**公开内容快照**与可选的合成演示数据，供本地启动器直接使用。这里没有任何真实用户数据。

## release-preview.db（默认）

本地启动器使用的公开快照。内容是**系统导入的公开信息**：公开事项、原文归档与版本、证据摘录、发布记录、来源与栏目配置。

导出时已清空的个人相关表：用户画像、个人计划与准备事项、订阅、提醒与通知、对话与消息、纠错记录、团队与任务、稿件、运行审计与心跳。这也是 `scripts/export_demo_data.py` 的强制检查项——只要有非公开文档或个人数据没清干净，导出会直接报错退出，不会生成不干净的快照。

启动器把这份快照复制成工作副本 `local-data/demo.db`，你自己的计划和后续采集数据都写在工作副本里，**这份快照始终不被修改**。

### 从自己的数据库导出同样的快照

```bash
backend/.venv/bin/python scripts/export_demo_data.py your.db --output demo-data/release-preview.db
```

导出完成后会在同目录生成 `data-package-report.json`，记录 schema 版本、各表行数和被清空的私有表行数，便于核对。

## 合成演示数据（可选）

需要一份带用户、计划、订阅、对话的完整演示数据时，可以用种子脚本自造。这些数据全部是虚构的，会明确标记批次名 `demo-five-people-20260929`，便于识别和整体删除。

```bash
# 1. 建一个独立数据库并迁移
export DATABASE_URL="sqlite:///$PWD/demo-data/retained-demo.db"
export DEMO_MODE=true ADMIN_USER_IDS=demo-user
cd backend && .venv/bin/python -m alembic upgrade head && cd ..

# 2. 生成 5 位模拟学生、3 条模拟事项、计划与订阅
backend/.venv/bin/python scripts/seed_retained_demo.py

# 3. 可选：追加可回放的助手会话样例
backend/.venv/bin/python scripts/seed_retained_agent.py

# 4. 启动
bash scripts/start_retained_demo.sh
```

种子脚本会强制校验 `DEMO_MODE=true` 且数据库路径含 `retained-demo`，**不会**写入其他数据库。

| 层次 | 数量 |
|---|---|
| 模拟学生 | 5（统计学、计算机科学、产品设计、机械工程、英语） |
| 模拟事项 | 3（岗位、升学申请、创业征集），每位学生各订阅 3 条 |
| 个人计划 / 订阅 | 15 / 15 |
| 助手会话（可选） | 5 个会话、10 轮对话 |

五位学生通过演示 API 的 `x-user-id` 请求头切换，浏览器默认身份是管理员 `demo-user`。

## 删除

- **删单条内容**：`/admin/data` 按测试批次筛选，点"管理员删除"。软删除，保留原文与审计。
- **删整份合成数据**：停掉服务后直接删掉 `demo-data/retained-demo.db` 即可，不影响其他数据库。

## 注意

这些数据是公开信息或合成数据，**不是真实用户数据，也不是经人工核验的招生或招聘结论**。演示身份不要用于任何公开部署；`DEMO_MODE=true` 会让 `x-user-id` 头直接决定身份，只适合隔离的本地环境。

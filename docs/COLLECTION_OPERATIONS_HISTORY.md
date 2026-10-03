# 采集运维历史记录

以下为原本地分支截至 2026-10-03 的操作记录，描述的是此前开发环境；合并本 PR 不会创建这些部署、定时任务或备份。当前仓库迁移编号为 0031–0033，启动与整合说明见 [数据接入进度](DATA_COLLECTION_PROGRESS.md)。

## 2026-10-03：附件、通知与异地备份补齐

API、Worker 和监控均已升级到迁移 `0030`。Docker 安装 antiword／catdoc、Tesseract 中文／英文及 Poppler；Python 增加 Pillow、xlrd、olefile。持续队列支持 PDF、DOC／DOCX、XLS／XLSX、单帧 PNG／JPEG／WEBP 正文图片。扫描图片不自动确定申请日期；旧 XLS 的公式单元格显示待核对标记，宏、加密内容和损坏容器保留诊断并等待人工核对。SQLite 使用 WAL 和 30 秒繁忙等待，PostgreSQL 不受此设置影响。

外部通知有持久队列、按告警事件去重、失败重试、租约恢复和恢复通知。当前本机 `.env` 使用 `COLLECTION_ALERT_CHANNEL=desktop`，通过 Mac 通知中心发送汇总，统计变化不重复推送同一故障。`scripts/cloud_watch.py` 独立检查云端 API、Worker、监控和两类备份；已安装 `~/Library/LaunchAgents/com.campusmate.collection.watch.plist`，每 300 秒运行，日志在 `local-data/cloud-watch*.log`。云端 `/v1/collection-exchange/health` 需要原文交换令牌，不公开账户或密钥。

若希望本机关机后也能接收通知，在 `collection-monitor` 私密变量中设置 `COLLECTION_ALERT_WEBHOOK` 和 `COLLECTION_ALERT_CHANNEL=feishu|wecom|telegram|generic`；Telegram 另需 `COLLECTION_ALERT_CHAT_ID`。接收地址尚未提供，Railway 的直接 Webhook 外发目前未启用。不要把含令牌的 URL 放进文档、命令日志或代码。

Railway 每日备份继续使用独立 `/backups` 卷和完整临时库恢复校验，并额外生成 age 加密文件及 SHA256。`BACKUP_AGE_RECIPIENT` 为公开收件人密钥，私钥仅在本机 `~/.ssh/campusmate-backup.agekey`，权限 600。新备份任务已手动运行：迁移 0030、3,207 份文档、2,495 条 published 记录、3,291 个队列资源，所有原件哈希一致。`artifacts/source-expansion-round8/backup-restore.log` 保存真实执行证据。

`scripts/offsite_mirror.py` 已实际通过 SSH 导出 Railway PostgreSQL 并在本机加密，解密后验证 PostgreSQL 恢复目录。加密副本在 `local-data/offsite-backups/`，约保留 30 天；`latest.json` 记录哈希与验证结果。已安装 `~/Library/LaunchAgents/com.campusmate.collection.backup.plist`，本机每天 03:15 运行，开机时补检查；20 小时内已有成功副本时跳过。本机须开机且联网。私钥须由运营者另存妥善位置，丢失私钥无法解密。

S3／R2 自动上传机制已经部署并通过上传后完整下载校验测试。若使用独立对象存储，在 `collection-backup` 私密变量中设置 `BACKUP_S3_BUCKET`、`BACKUP_S3_ENDPOINT`（S3 可省略）、`BACKUP_S3_PREFIX`、`AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_DEFAULT_REGION`；加密收件人沿用 `BACKUP_AGE_RECIPIENT`。可设置 `BACKUP_OFFSITE_REQUIRED=true`，缺配置或读回哈希失败会使任务明确失败，同时保留已验证的卷上副本。当前未提供对象存储配置，上传未启用，现有异地副本位于 Mac。

仅公开父公告明确链接的原件可参与附件交换。接收端核对来源、父公告当前公开状态、父原文哈希、附件链接及附件 SHA256，再用自己的解析器处理；无账户、私有上传、人工审核结论或资格规则同步。支持文件不单独创建申请机会，交换不冒充云端成功访问官网。

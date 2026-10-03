import { privateApi } from "@/lib/session-api";
export default async function Operations() {
  const data = await privateApi('/v1/admin/operations');
  return <div className="shell page"><h1>运行状态</h1><p>此页面刷新时重新读取数据库。Worker 超过 120 秒没有成功心跳会显示异常。</p><div className="cards"><article className="card"><h2>提醒服务</h2><p>{data.worker.healthy ? "正常" : "需要检查"}</p><p>状态：{data.worker.state}</p><p>心跳距今：{data.worker.age_seconds === null ? "从未启动" : `${Math.round(data.worker.age_seconds)} 秒`}</p></article><article className="card"><h2>待发送提醒</h2><p>{data.pending_reminders}</p></article><article className="card"><h2>有效已发布机会</h2><p>{data.published_opportunities}</p></article></div></div>;
}

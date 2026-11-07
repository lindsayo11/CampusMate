type Topic = {topic:string;label:string;enabled_sources:number;healthy_sources:number;public_items:number;application_notices:number;open:number;upcoming:number;needs_confirmation:number};
export type CoverageQualityData = {
  topics:Topic[]; unmonitored_items:number; details_discovered:number; details_collected:number;
  detail_success_rate:number|null; application_notices:number; dated_notices:number;
  deadline_completeness:number|null; availability:Record<string,number>; enabled_sources:number;
  stale_sources:number; error_categories:Record<string,number>;
  unsuccessful_sources?:number;attempts_24h?:number;successful_attempts_24h?:number;
  attempt_success_rate_24h?:number|null;active_alerts?:number;monitor_status?:string;
  worker:{status:string;observed_at:string|null};
  sync?:{state:string;mode?:string;pulled:number;pushed:number;pending:number;error?:string;last_success_at:string|null;interval_minutes:number};
  attachments?:{archived:number;waiting:number;ocr_documents:number;formats:Record<string,number>};
  alert_delivery?:{channel:string;pending:number;delivered:number};
  backups?:Record<string,{state:string;last_verified_at:string|null}>;
};
const percent = (value:number|null) => value===null?'暂无数据':`${value}%`;
const workerLabels:Record<string,string> = {ok:'运行正常',error:'最近运行异常',stale:'心跳超时',unknown:'尚无运行记录'};
const errors:Record<string,string> = {access_denied:'访问边界或登录限制',network:'网络与失效链接',ocr_required:'扫描件待识别',title_or_topic:'标题或主题需核对',body_or_structure:'正文结构需适配'};
const syncLabels:Record<string,string> = {ok:'正常',partial:'部分内容等待重试',error:'连接异常',stale:'检查超时',pending:'等待首次同步',running:'正在同步'};

export function CoverageQuality({data}:{data:CoverageQualityData}) {
  return <section className="topic-section">
    <h2>覆盖与采集质量</h2>
    <div className="coverage-summary">
      <section className="card"><strong>{percent(data.detail_success_rate)}</strong><p>正文任务已解析比例</p><p className="form-help">{data.details_collected}／{data.details_discovered} 个正文任务</p></section>
      <section className="card"><strong>{percent(data.deadline_completeness)}</strong><p>申请通知截止日期完整度</p><p className="form-help">{data.dated_notices}／{data.application_notices} 条有明确截止日期</p></section>
      <section className="card"><strong>{data.availability.open||0}</strong><p>已知申请窗口内的通知</p><p className="form-help">尚未开始 {data.availability.upcoming||0} · 日期待确认 {data.availability.needs_confirmation||0}</p></section>
    </div>
    <p>后台采集：{workerLabels[data.worker.status]||'状态待确认'}。已开启 {data.enabled_sources} 个来源，其中 {data.stale_sources} 个超过两轮检查间隔未更新。申请窗口仅依据原文明示日期，不代表申请资格已核验。</p>
    <p>最近 24 小时成功检查 {data.successful_attempts_24h||0}／{data.attempts_24h||0} 次，成功率 {percent(data.attempt_success_rate_24h??null)}。{data.unsuccessful_sources||0} 个来源尚未成功检查或成功记录已超时。独立告警监测{data.monitor_status==='ok'?'正常':'待检查'}，当前 {data.active_alerts||0} 项告警。</p>
    {data.sync&&data.sync.state!=='not_configured'&&<section className="card"><h3>官方原文同步</h3><p>{syncLabels[data.sync.state]||'状态待确认'}{data.sync.mode==='bidirectional'?` · 每 ${data.sync.interval_minutes} 分钟与云端互补采集结果`:' · 接收其他已授权采集端的官方原文'}。累计接收 {data.sync.pulled} 条{data.sync.mode==='bidirectional'&&`，发送 ${data.sync.pushed} 条，${['error','stale','running'].includes(data.sync.state)?'上次清点待处理':'待处理'} ${data.sync.pending} 条`}。</p>{data.sync.error&&<p role="status">{data.sync.error}</p>}<p className="form-help">最近完成：{data.sync.last_success_at?new Date(data.sync.last_success_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}):'尚无记录'}。仅同步公开原文，接收后重新解析；同步不计为本站成功访问官方来源。</p></section>}
    {data.attachments&&<section className="card"><h3>附件与图片识别</h3><p>已归档 {data.attachments.archived} 份辅助附件，{data.attachments.waiting} 份等待采集；{data.attachments.ocr_documents} 份当前文档包含 OCR 证据。</p><p className="form-help">支持 PDF、DOC／DOCX、XLS／XLSX 和正文图片，保留原件、父公告及页码／行号／识别框。OCR 日期仍需核对，附件不单独创建申请机会。</p></section>}
    {data.alert_delivery&&<section className="card"><h3>告警通知与备份</h3><p>通知渠道：{data.alert_delivery.channel==='desktop'?'Mac 桌面通知':data.alert_delivery.channel==='not_configured'?'尚未配置':data.alert_delivery.channel}。已发送 {data.alert_delivery.delivered} 项状态变化，等待发送 {data.alert_delivery.pending} 项；状态不变时保持安静。</p>{data.backups&&Object.entries(data.backups).map(([key,backup])=><p key={key}>{key==='offsite'?'Railway 以外的加密副本':'Railway 数据库备份'}：{backup.state==='ok'?'最近验证正常':backup.state==='stale'?'验证记录已超时':'尚无验证记录'}。{backup.last_verified_at&&new Date(backup.last_verified_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}</p>)}<p className="form-help">Mac 通知、云端独立巡检和本机异地副本需要本机开机并联网；云端采集与 Railway 每日备份独立运行。</p></section>}
    <div className="coverage-table-wrap"><table className="coverage-table">
      <thead><tr><th>领域</th><th>开启／栏目正常</th><th>公开条目</th><th>窗口内／尚未开始</th><th>日期待确认</th></tr></thead>
      <tbody>{data.topics.map(t=><tr key={t.topic}><td>{t.label}</td><td>{t.enabled_sources}／{t.healthy_sources}</td><td>{t.public_items}</td><td>{t.open}／{t.upcoming}</td><td>{t.needs_confirmation}</td></tr>)}</tbody>
    </table></div>
    <p className="form-help">按已配置监测来源归类，包含历史和过期内容；另有 {data.unmonitored_items} 条来自尚未配置监测的来源。正文比例包含已发现的排队和失败任务；PDF 附件单独入库，不计作 HTML 正文任务成功。</p>
    <details><summary>查看采集异常分类</summary>{Object.entries(errors).map(([key,label])=><p key={key}>{label}：{data.error_categories[key]||0} 项</p>)}</details>
  </section>;
}

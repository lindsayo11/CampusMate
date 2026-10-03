import { privateApi } from "@/lib/session-api";
import { EndpointHealth, SourceEndpointControls } from "@/components/source-endpoint-controls";
import { EndpointCalibrationControls } from "@/components/endpoint-calibration-controls";

type Source = {
  id: string;
  source_code: string;
  name: string;
  publisher: string;
  authority_level: string;
  official: boolean;
  jurisdiction_level: string;
  supported_paths: string[];
  base_url: string;
  active: boolean;
  verified_at: string;
};

export default async function RegistryPage() {
  const [sources, health] = await Promise.all([
    privateApi("/v1/sources?limit=200") as Promise<Source[]>,
    privateApi("/v1/admin/intake/health") as Promise<EndpointHealth[]>,
  ]);
  const endpoints = new Map<string, EndpointHealth[]>();
  for (const item of health) endpoints.set(item.source_id, [...(endpoints.get(item.source_id) || []), item]);
  return <div className="shell page">
    <p className="eyebrow">数据源治理</p>
    <h1>SourceRegistry 与端点健康</h1>
    <p className="lead">核对发布者、权威等级、采集边界和端点状态。登录型端点只用于用户操作，不进入后台采集。</p>
    {sources.map(source => <article className="card" key={source.id}>
      <h2>{source.source_code} · {source.name}</h2>
      <p>{source.publisher} · 权威 {source.authority_level} · {source.official ? "官方" : "非官方"} · {source.jurisdiction_level}</p>
      <p>路径：{source.supported_paths.join("、") || "未配置"} · 核验：{new Date(source.verified_at).toLocaleDateString("zh-CN")}</p>
      <a href={source.base_url} target="_blank" rel="noreferrer">打开官方入口</a>
      {(endpoints.get(source.id) || []).map(endpoint => <div key={endpoint.id}>
        <strong>{endpoint.name}</strong> · <span className={`risk ${endpoint.status === "healthy" ? "low" : endpoint.status === "failed" ? "high" : "medium"}`}>{endpoint.status}</span>
        <p>{endpoint.automation_level} · {endpoint.auth_type} · {endpoint.fetch_interval} · {endpoint.scheduled ? "已调度" : endpoint.manual_takeover ? "人工接管" : "未调度"}</p>
        <p>许可证：{endpoint.license_status}{endpoint.license_note ? ` · ${endpoint.license_note}` : ""}</p>
        <p>失败 {endpoint.consecutive_failures} 次 · 最近成功：{endpoint.last_success_at ? new Date(endpoint.last_success_at).toLocaleString("zh-CN") : "尚未同步"} · 下次：{endpoint.next_run_at ? new Date(endpoint.next_run_at).toLocaleString("zh-CN") : "无"}</p>
        {(endpoint.last_error || endpoint.paused_reason) && <p>{endpoint.last_error || endpoint.paused_reason}</p>}
        <a href={endpoint.url} target="_blank" rel="noreferrer">核对端点</a>
        <EndpointCalibrationControls endpoint={endpoint}/>
        <SourceEndpointControls endpoint={endpoint}/>
      </div>)}
    </article>)}
  </div>;
}

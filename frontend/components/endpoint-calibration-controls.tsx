"use client";

import { useState } from "react";
import { apiBase } from "@/lib/api";
import type { EndpointHealth } from "@/components/source-endpoint-controls";

async function request(path: string, method: string, body: unknown) {
  const response = await fetch(apiBase + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw Error(typeof data.detail === "string" ? data.detail : "操作失败");
  return data;
}

export function EndpointCalibrationControls({ endpoint }: { endpoint: EndpointHealth }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [record, setRecord] = useState<string>("");

  async function submit() {
    if (busy) return;
    setBusy(true); setMessage("");
    try {
      const exactUrl = window.prompt("精确、匿名公开的官方页面 URL", endpoint.url);
      if (!exactUrl) throw Error("已取消提交");
      const mappingText = window.prompt("字段映射 JSON（至少一项）", '{"title":"h1"}');
      if (mappingText === null) throw Error("已取消提交");
      const configText = window.prompt("Adapter 配置 JSON", "{}");
      if (configText === null) throw Error("已取消提交");
      const proofText = window.prompt("请粘贴核验依据 JSON，必须逐项提供原文 URL、逐字摘录和实际下载文件的 SHA256，不得填写猜测值", JSON.stringify({
        robots_url: "", robots_quote: "", terms_url: "", terms_quote: "",
        license_url: "", license_quote: "", page_sha256: "",
      }, null, 2));
      if (!proofText) throw Error("已取消提交");
      const robots = window.prompt("robots 结论：allowed / disallowed / unknown", "unknown");
      const terms = window.prompt("条款结论：permitted / restricted / unknown", "unknown");
      const license = window.prompt("许可证结论：permitted / restricted / unknown", "unknown");
      await request(`/v1/admin/intake/endpoints/${endpoint.id}/calibrations`, "POST", {
        exact_url: exactUrl,
        robots_status: robots,
        terms_status: terms,
        license_status: license,
        proof: JSON.parse(proofText),
        field_mapping: JSON.parse(mappingText),
        adapter_config: JSON.parse(configText),
      });
      setMessage("校准记录已提交，等待两名不同管理员审核");
      window.location.reload();
    } catch (error) {
      setMessage(error instanceof SyntaxError ? "字段映射或 Adapter 配置不是有效 JSON" : (error as Error).message);
    } finally { setBusy(false); }
  }

  async function inspect() {
    try {
      const response = await fetch(`${apiBase}/v1/admin/intake/calibrations?endpoint_id=${endpoint.id}`);
      if (!response.ok) throw Error("读取校准依据失败");
      setRecord(JSON.stringify(await response.json(), null, 2));
    } catch (error) { setMessage((error as Error).message); }
  }

  async function review(action: "approve" | "reject") {
    if (!endpoint.calibration_id || busy) return;
    setBusy(true); setMessage("");
    try {
      const note = window.prompt("填写审核依据", action === "approve" ? "已复核原始页面与使用边界" : "校准证据不足") || "";
      await request(`/v1/admin/intake/calibrations/${endpoint.calibration_id}`, "PATCH", { action, note });
      setMessage(action === "approve" ? "审核已记录；满足双人要求后自动关闭校准阻塞" : "校准已驳回");
      window.location.reload();
    } catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }

  return <div>
    {endpoint.calibration_status !== "pending" &&
      <button disabled={busy} onClick={submit}>提交线上校准</button>}
    <button onClick={inspect}>查看校准原始依据</button>
    {record && <details open><summary>校准记录与证据（先核对再审核）</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{record}</pre></details>}
    {endpoint.calibration_status === "pending" && <>
      <button disabled={busy || !record} onClick={() => review("approve")}>审核通过</button>
      <button disabled={busy} onClick={() => review("reject")}>驳回校准</button>
    </>}
    {endpoint.open_blockers > 0 && <span>开放阻塞 {endpoint.open_blockers} 项</span>}
    {endpoint.calibration_status && <span>校准：{endpoint.calibration_status}</span>}
    {message && <span role="status">{message}</span>}
  </div>;
}

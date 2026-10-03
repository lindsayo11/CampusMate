"use client";

import { useState } from "react";
import { apiBase } from "@/lib/api";

export type EndpointHealth = {
  id: string;
  source_id: string;
  name: string;
  url: string;
  active: boolean;
  scheduled: boolean;
  manual_takeover: boolean;
  last_success_at: string | null;
  last_attempt_at: string | null;
  next_run_at: string | null;
  consecutive_failures: number;
  paused_reason: string;
  last_error: string;
  auth_type: string;
  license_status: string;
  license_note: string;
  automation_level: string;
  agent_mode: string;
  fetch_interval: string;
  parser_type: string;
  access_tags: string[];
  open_blockers: number;
  calibration_status: "pending" | "approved" | "rejected" | null;
  calibration_id: string | null;
  gate_reason: string | null;
  status: "healthy" | "stale" | "failed" | "disabled";
};

export function SourceEndpointControls({ endpoint }: { endpoint: EndpointHealth }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const eligible = endpoint.auth_type === "none" && ["AUTO-1", "AUTO-2"].includes(endpoint.automation_level)
    && endpoint.agent_mode !== "USER_ACTION"
    && endpoint.license_status !== "restricted"
    && !endpoint.access_tags.some(tag => ["LOGIN-USER", "COMMERCIAL", "LICENSE"].includes(tag))
    && !endpoint.gate_reason && endpoint.open_blockers === 0;

  async function call(path: string, method: string, body?: unknown) {
    const response = await fetch(apiBase + path, {
      method, headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === "string" ? data.detail : "操作失败");
    return data;
  }

  async function control(action: "enable" | "resume" | "pause" | "takeover") {
    if (busy) return;
    setBusy(true); setMessage("");
    try {
      let url: string | undefined;
      let adapter_config: Record<string, unknown> = {};
      if (action === "enable" || action === "resume") {
        url = window.prompt("请确认精确、公开、允许采集的官方端点 URL", endpoint.url) || undefined;
        if (!url) throw Error("已取消启用");
        if (["CivilServiceWorkbookAdapter", "OverseasUniversityProgramAdapter"].includes(endpoint.parser_type)) {
          const hint = endpoint.parser_type === "OverseasUniversityProgramAdapter"
            ? "必须包含 institution_id、program_code、program_name、path_code"
            : "必须包含 cycle_code、cycle_name、cycle_year";
          const raw = window.prompt(`请输入 Adapter 配置 JSON，${hint}`, "{}");
          if (raw === null) throw Error("已取消启用");
          adapter_config = JSON.parse(raw);
        }
      }
      const reason = window.prompt("请填写本次操作依据", "管理员核验") || "管理员核验";
      await call(`/v1/admin/intake/endpoints/${endpoint.id}`, "PATCH",
        { action, reason, ...(url ? { url } : {}), adapter_config });
      setMessage("操作已保存"); window.location.reload();
    } catch (error) { setMessage(error instanceof SyntaxError ? "Adapter 配置不是有效 JSON" : (error as Error).message); }
    finally { setBusy(false); }
  }

  async function run() {
    if (busy) return;
    setBusy(true); setMessage("");
    try { await call(`/v1/admin/intake/endpoints/${endpoint.id}/run`, "POST"); setMessage("已加入采集队列"); }
    catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }

  return <div className="actions">
    {!endpoint.scheduled && !endpoint.manual_takeover && <button disabled={busy || !eligible} onClick={() => control("enable")}>核验并启用</button>}
    {endpoint.scheduled && <><button disabled={busy} onClick={run}>立即采集</button><button disabled={busy} onClick={() => control("pause")}>暂停</button><button disabled={busy} onClick={() => control("takeover")}>人工接管</button></>}
    {endpoint.manual_takeover && <button disabled={busy || !eligible} onClick={() => control("resume")}>核验后恢复</button>}
    {!eligible && <span>{endpoint.gate_reason || "该端点按权限边界禁止后台调度"}</span>}
    {message && <span role="status">{message}</span>}
  </div>;
}

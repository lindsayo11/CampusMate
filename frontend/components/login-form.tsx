"use client";
import { useState } from "react";
export default function Login() {
  const [message, setMessage] = useState("");
  const [signup, setSignup] = useState(false);
  const [busy, setBusy] = useState(false);
  return <div className="shell auth-page"><h1>{signup ? "创建校伴账号" : "登录校伴"}</h1><p>使用邮箱注册并完成邮件确认。学校信息由本人填写，不代表学籍认证。</p><form className="form-card" onSubmit={async e => {
    e.preventDefault(); if (busy) return; const f = new FormData(e.currentTarget); setBusy(true); setMessage("处理中…");
    try {
      const r = await fetch("/api/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: f.get("email"), password: f.get("password"), action: signup ? "signup" : "login" }) });
      const data = await r.json();
      if (!r.ok) setMessage(data.detail); else if (data.confirmation_required) setMessage(data.message); else location.assign("/profile");
    } catch { setMessage("网络错误，请重试"); } finally { setBusy(false); }
  }}><label>邮箱<input required name="email" type="email" maxLength={254} autoComplete="username" /></label><label>密码<input required name="password" type="password" minLength={signup ? 8 : 1} maxLength={1024} autoComplete={signup ? "new-password" : "current-password"} /></label><button disabled={busy}>{busy ? "处理中…" : signup ? "注册" : "登录"}</button></form><button disabled={busy} onClick={() => { setSignup(!signup); setMessage(""); }}>{signup ? "已有账号，去登录" : "没有账号，去注册"}</button><button disabled={busy} onClick={async () => {
    setBusy(true); try { const r = await fetch("/api/session", { method: "DELETE" }); const data = await r.json(); setMessage(data.message || data.detail); } catch { setMessage("网络错误，请重试"); } finally { setBusy(false); }
  }}>退出当前会话</button><p><a href="/recover">忘记密码？</a></p><p role="status" aria-live="polite">{message}</p></div>;
}

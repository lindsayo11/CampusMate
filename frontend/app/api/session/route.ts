import { NextRequest, NextResponse } from "next/server";
import { AuthError, authFailure, authRequest, clearSession, parseSession, refreshSession, sameOrigin, setSession } from "@/lib/auth-session";
export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  try {
    let input;
    try { input = await req.json(); } catch { throw new AuthError(422, "输入无效"); }
    const { email, password, action = "login" } = input || {};
    if (!["login", "signup"].includes(action) || typeof email !== "string" || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254 || typeof password !== "string" || !password || password.length > 1024 || (action === "signup" && password.length < 8)) throw new AuthError(422, "请输入有效邮箱；注册密码至少 8 位");
    const data = await authRequest(action === "signup" ? "signup" : "token?grant_type=password", { email, password });
    if (action === "signup" && !data.access_token) return NextResponse.json({ ok: true, confirmation_required: true, message: "如该邮箱可以注册，请查看确认邮件，确认后返回登录。" }, { headers: { "Cache-Control": "no-store" } });
    const response = NextResponse.json({ ok: true });
    setSession(response, parseSession(data));
    return response;
  } catch (e) { return authFailure(e); }
}
export async function PATCH(req: NextRequest) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  const token = req.cookies.get("cm_refresh")?.value;
  if (!token) return NextResponse.json({ detail: "请重新登录" }, { status: 401 });
  try {
    const response = NextResponse.json({ ok: true });
    setSession(response, await refreshSession(token));
    return response;
  } catch (e) { const response = authFailure(e); if (response.status === 401) clearSession(response); return response; }
}
export async function DELETE(req: NextRequest) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Invalid origin" }, { status: 403 });
  let revoked = true;
  try {
    let token = req.cookies.get("cm_access")?.value;
    const refresh = req.cookies.get("cm_refresh")?.value;
    if (refresh) token = (await refreshSession(refresh)).access_token;
    if (token) await authRequest("logout?scope=local", undefined, token);
  } catch { revoked = false; }
  const response = NextResponse.json({ ok: true, revoked, message: revoked ? "已退出登录" : "本机已退出；远端会话撤销失败，请在账号服务中检查会话。" });
  clearSession(response);
  return response;
}

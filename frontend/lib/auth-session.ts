import { NextRequest, NextResponse } from "next/server";

export type Session = { access_token: string; refresh_token: string; expires_in: number };
export class AuthError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export function sameOrigin(req: NextRequest) {
  const configured = process.env.APP_ORIGIN;
  return req.headers.get("origin") === (configured || req.nextUrl.origin);
}
export async function authRequest(path: string, body?: unknown, access?: string, method: "POST" | "PUT" = "POST") {
  const url = process.env.SUPABASE_URL, key = process.env.SUPABASE_ANON_KEY;
  if (!url?.startsWith("https://") || !key) throw new AuthError(503, "尚未配置身份服务");
  let response: Response;
  try {
    response = await fetch(`${url.replace(/\/$/, "")}/auth/v1/${path}`, {
      method, headers: { apikey: key, "Content-Type": "application/json", ...(access ? { Authorization: `Bearer ${access}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body), cache: "no-store", redirect: "error", signal: AbortSignal.timeout(10000),
    });
  } catch { throw new AuthError(503, "身份服务暂不可用，请稍后重试"); }
  if (!response.ok) {
    if (response.status === 429) throw new AuthError(429, "操作过于频繁，请稍后重试");
    if (response.status >= 500) throw new AuthError(503, "身份服务暂不可用，请稍后重试");
    throw new AuthError(401, "身份验证失败，请检查输入或重新登录");
  }
  if (response.status === 204) return {};
  try { return await response.json(); } catch { throw new AuthError(503, "身份服务响应无效"); }
}
export function parseSession(data: unknown): Session {
  const s = data as Partial<Session> | null;
  if (!s || typeof s.access_token !== "string" || !s.access_token || typeof s.refresh_token !== "string" || !s.refresh_token || typeof s.expires_in !== "number" || !Number.isFinite(s.expires_in) || s.expires_in <= 0)
    throw new AuthError(503, "身份服务响应无效");
  return s as Session;
}
const options = () => ({ httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax" as const, path: "/" });
export function setSession(response: NextResponse, session: Session) {
  // Retain the expired access token so the server can distinguish expiry from no session.
  response.cookies.set("cm_access", session.access_token, { ...options(), maxAge: 60 * 60 * 24 * 30 });
  response.cookies.set("cm_refresh", session.refresh_token, { ...options(), maxAge: 60 * 60 * 24 * 30 });
  response.cookies.set("cm_expires", String(Date.now() + session.expires_in * 1000), { ...options(), maxAge: 60 * 60 * 24 * 30 });
  response.headers.set("Cache-Control", "private, no-store");
}
export function clearSession(response: NextResponse) {
  for (const name of ["cm_access", "cm_refresh", "cm_expires"]) response.cookies.set(name, "", { ...options(), maxAge: 0 });
  response.headers.set("Cache-Control", "private, no-store");
}
export function authFailure(error: unknown) {
  const e = error instanceof AuthError ? error : new AuthError(503, "身份服务暂不可用");
  return NextResponse.json({ detail: e.message }, { status: e.status, headers: { "Cache-Control": "no-store" } });
}
// Coalesce concurrent refreshes within a process without persisting credentials.
const refreshing = new Map<string, Promise<Session>>();
export async function refreshSession(token: string) {
  let pending = refreshing.get(token);
  if (!pending) {
    pending = authRequest("token?grant_type=refresh_token", { refresh_token: token }).then(parseSession);
    refreshing.set(token, pending);
  }
  try { return await pending; } finally { refreshing.delete(token); }
}

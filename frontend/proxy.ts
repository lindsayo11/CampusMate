import { NextRequest, NextResponse } from "next/server";
import { AuthError, clearSession, refreshSession, setSession } from "./lib/auth-session";
export async function proxy(req: NextRequest) {
  const path=req.nextUrl.pathname;
  const frozen=(path==="/agent"||path.startsWith("/agent/"))&&process.env.ENABLE_AGENT_UI!=="true"
    ||(path==="/admin/collector"||path.startsWith("/admin/collector/"))&&process.env.ENABLE_COLLECTOR_UI!=="true";
  if(frozen)return NextResponse.rewrite(new URL("/_not-found",req.url),{status:404});
  const token = req.cookies.get("cm_refresh")?.value;
  const expires = Number(req.cookies.get("cm_expires")?.value || 0);
  if (!token || expires > Date.now() + 60000) return NextResponse.next();
  try {
    const session = await refreshSession(token);
    req.cookies.set("cm_access", session.access_token);
    req.cookies.set("cm_refresh", session.refresh_token);
    req.cookies.set("cm_expires", String(Date.now() + session.expires_in * 1000));
    const response = NextResponse.next({ request: { headers: new Headers(req.headers) } });
    setSession(response, session);
    return response;
  } catch (error) {
    if (error instanceof AuthError && error.status === 401) {
      for (const name of ["cm_access", "cm_refresh", "cm_expires"]) req.cookies.delete(name);
      const response = NextResponse.next({ request: { headers: new Headers(req.headers) } });
      clearSession(response);
      return response;
    }
    return NextResponse.json({ detail: "身份服务暂不可用，请刷新重试" }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
export const config = { matcher: ["/((?!api/session|recover|_next/static|_next/image|favicon.svg|favicon.ico).*)"] };

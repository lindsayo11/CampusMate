import { NextRequest, NextResponse } from "next/server";
import { AuthError, parseSession, setSession } from "@/lib/auth-session";

const verifierCookie = "cm_oauth_verifier";
const stateCookie = "cm_oauth_state";
const nextCookie = "cm_oauth_next";

function clearOAuthCookies(response: NextResponse) {
  for (const name of [verifierCookie, stateCookie, nextCookie]) response.cookies.set(name, "", { httpOnly: true, secure: process.env.APP_ORIGIN?.startsWith("https://") === true, sameSite: "lax", path: "/auth/callback", maxAge: 0 });
}

function safeNext(value: string | undefined) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/settings";
}

export async function GET(req: NextRequest) {
  const origin = process.env.APP_ORIGIN || req.nextUrl.origin;
  const destination = safeNext(req.cookies.get(nextCookie)?.value);
  const authOrigin = process.env.AUTH_ORIGIN || origin;
  const fail = (reason: string) => {
    const response = NextResponse.redirect(new URL(`/login.html?oauth_error=${encodeURIComponent(reason)}`, authOrigin));
    clearOAuthCookies(response);
    return response;
  };
  if (req.nextUrl.searchParams.get("error")) return fail("provider_denied");

  const code = req.nextUrl.searchParams.get("code");
  const state = req.nextUrl.searchParams.get("state");
  const expectedState = req.cookies.get(stateCookie)?.value;
  const verifier = req.cookies.get(verifierCookie)?.value;
  if (!code || !state || !expectedState || state !== expectedState || !verifier) return fail("invalid_callback");

  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_ANON_KEY;
  if (!supabaseUrl?.startsWith("https://") || !supabaseKey) return fail("not_configured");

  try {
    const response = await fetch(`${supabaseUrl.replace(/\/$/, "")}/auth/v1/token?grant_type=pkce`, {
      method: "POST",
      headers: { apikey: supabaseKey, "Content-Type": "application/json" },
      body: JSON.stringify({ auth_code: code, code_verifier: verifier }),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) {
      // Keep provider details out of the browser, but expose the status class so local setup errors are diagnosable.
      throw new AuthError(response.status >= 500 ? 503 : 401, `OAuth exchange failed (${response.status})`);
    }
    const session = parseSession(await response.json());
    const result = NextResponse.redirect(new URL(destination, origin));
    setSession(result, session);
    clearOAuthCookies(result);
    return result;
  } catch (error) {
    const status = error instanceof AuthError && /\((\d{3})\)/.test(error.message) ? error.message.match(/\((\d{3})\)/)?.[1] : undefined;
    return fail(status ? `exchange_failed_${status}` : "exchange_failed");
  }
}

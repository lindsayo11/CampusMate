import { createHash, randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

const verifierCookie = "cm_oauth_verifier";
const stateCookie = "cm_oauth_state";
const nextCookie = "cm_oauth_next";

function cookieOptions() {
  return { httpOnly: true, secure: process.env.APP_ORIGIN?.startsWith("https://") === true, sameSite: "lax" as const, path: "/auth/callback", maxAge: 600 };
}

function safeNext(value: string | null) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/settings";
}

export function GET(req: NextRequest) {
  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_ANON_KEY;
  const authOrigin = process.env.AUTH_ORIGIN || process.env.APP_ORIGIN || req.nextUrl.origin;
  if (!supabaseUrl?.startsWith("https://") || !supabaseKey) return NextResponse.redirect(new URL("/login.html?oauth_error=not_configured", authOrigin));

  const origin = (process.env.APP_ORIGIN || req.nextUrl.origin).replace(/\/$/, "");
  const verifier = randomBytes(32).toString("base64url");
  const challenge = createHash("sha256").update(verifier).digest("base64url");
  const state = randomBytes(24).toString("base64url");
  const callback = new URL(`${origin}/auth/callback`);
  callback.searchParams.set("state", state);
  const authorize = new URL(`${supabaseUrl.replace(/\/$/, "")}/auth/v1/authorize`);
  authorize.searchParams.set("provider", "google");
  authorize.searchParams.set("redirect_to", callback.toString());
  authorize.searchParams.set("code_challenge", challenge);
  authorize.searchParams.set("code_challenge_method", "s256");

  const response = NextResponse.redirect(authorize);
  const options = cookieOptions();
  response.cookies.set(verifierCookie, verifier, options);
  response.cookies.set(stateCookie, state, options);
  response.cookies.set(nextCookie, safeNext(req.nextUrl.searchParams.get("next")), options);
  return response;
}

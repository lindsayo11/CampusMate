import { afterEach, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { NextRequest } from "next/server";
import { GET as startOAuth } from "../app/api/session/oauth/route";
import { GET as finishOAuth } from "../app/auth/callback/route";

const originalFetch = globalThis.fetch;
const originalAuthOrigin = process.env.AUTH_ORIGIN;
const session = { access_token: "oauth-access", refresh_token: "oauth-refresh", expires_in: 3600 };

beforeEach(() => {
  process.env.SUPABASE_URL = "https://auth.test";
  process.env.SUPABASE_ANON_KEY = "public-test";
  process.env.APP_ORIGIN = "https://campus.test";
  process.env.AUTH_ORIGIN = "https://demo.test";
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalAuthOrigin === undefined) delete process.env.AUTH_ORIGIN; else process.env.AUTH_ORIGIN = originalAuthOrigin;
});

test("Google OAuth start creates PKCE redirect and HttpOnly cookies", async () => {
  const response = startOAuth(new NextRequest("https://campus.test/api/session/oauth?next=%2Fsettings"));
  assert.equal(response.status, 307);
  const location = new URL(response.headers.get("location")!);
  assert.equal(location.origin, "https://auth.test");
  assert.equal(location.searchParams.get("provider"), "google");
  const callback = new URL(location.searchParams.get("redirect_to")!);
  assert.equal(callback.origin, "https://campus.test");
  assert.equal(callback.pathname, "/auth/callback");
  assert.equal(callback.searchParams.get("state"), response.cookies.get("cm_oauth_state")?.value);
  assert.equal(location.searchParams.get("code_challenge_method"), "s256");
  assert.ok(location.searchParams.get("code_challenge"));
  assert.equal(location.searchParams.has("state"), false);
  assert.match(response.headers.get("set-cookie")!, /cm_oauth_verifier=/);
  assert.match(response.headers.get("set-cookie")!, /HttpOnly/);
});

test("Google OAuth callback exchanges code and sets the app session", async () => {
  const start = startOAuth(new NextRequest("https://campus.test/api/session/oauth?next=%2Fsettings"));
  const location = new URL(start.headers.get("location")!);
  const callbackUrl = new URL(location.searchParams.get("redirect_to")!);
  const cookies = start.cookies.getAll().map(cookie => `${cookie.name}=${cookie.value}`).join("; ");
  globalThis.fetch = async (url, init) => {
    assert.match(String(url), /auth\.test\/auth\/v1\/token\?grant_type=pkce$/);
    assert.match(String(init?.body), /auth_code/);
    assert.match(String(init?.body), /code_verifier/);
    return Response.json(session);
  };
  const callback = new NextRequest(`https://campus.test/auth/callback?code=verified-code&state=${callbackUrl.searchParams.get("state")}`, { headers: { cookie: cookies } });
  const response = await finishOAuth(callback);
  assert.equal(response.status, 307);
  assert.equal(response.headers.get("location"), "https://campus.test/settings");
  assert.equal(response.cookies.get("cm_access")?.value, "oauth-access");
  assert.equal(response.cookies.get("cm_refresh")?.value, "oauth-refresh");
  assert.equal(response.cookies.get("cm_oauth_verifier")?.maxAge, 0);
});

test("OAuth errors return to the 8080 login page", async () => {
  const response = startOAuth(new NextRequest("https://campus.test/api/session/oauth"));
  assert.equal(new URL(response.headers.get("location")!).origin, "https://auth.test");

  const failed = await finishOAuth(new NextRequest("https://campus.test/auth/callback?error=access_denied", { headers: { cookie: "cm_oauth_state=stale; cm_oauth_verifier=old" } }));
  assert.equal(failed.headers.get("location"), "https://demo.test/login.html?oauth_error=provider_denied");
  assert.equal(failed.cookies.get("cm_oauth_state")?.maxAge, 0);
});

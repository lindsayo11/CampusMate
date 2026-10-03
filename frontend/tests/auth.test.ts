import { afterEach, beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { NextRequest } from 'next/server';
import { POST, PATCH, DELETE } from '../app/api/session/route';
import { proxy } from '../proxy';
const originalFetch = globalThis.fetch;
const session = { access_token: 'access-new', refresh_token: 'refresh-new', expires_in: 3600 };
function request(method = 'POST', body: unknown = { email: 'student@example.edu', password: 'password123' }, cookie = '') {
  return new NextRequest('https://campus.test/api/session', { method, headers: { origin: 'https://campus.test', cookie }, body: method === 'DELETE' ? undefined : JSON.stringify(body) });
}
beforeEach(() => { process.env.SUPABASE_URL = 'https://auth.test'; process.env.SUPABASE_ANON_KEY = 'public-test'; });
afterEach(() => { globalThis.fetch = originalFetch; });
test('login keeps access and refresh tokens out of response body and sets HttpOnly cookies', async () => {
  globalThis.fetch = async () => Response.json(session);
  const r = await POST(request());
  assert.equal(r.status, 200); assert.deepEqual(await r.json(), { ok: true });
  assert.equal(r.cookies.get('cm_refresh')?.value, 'refresh-new');
  assert.match(r.headers.get('set-cookie')!, /HttpOnly/);
  assert.match(r.headers.get('cache-control')!, /no-store/);
});
test('signup confirmation response creates no session', async () => {
  globalThis.fetch = async (url) => { assert.match(String(url), /signup$/); return Response.json({ id: 'user' }); };
  const r = await POST(request('POST', { email: 'student@example.edu', password: 'password123', action: 'signup' }));
  assert.equal((await r.json()).confirmation_required, true); assert.equal(r.cookies.get('cm_access'), undefined);
});
test('bad input and cross-origin mutations never call auth', async () => {
  globalThis.fetch = async () => { throw Error('must not call'); };
  assert.equal((await POST(request('POST', { email: 'bad', password: 'x' }))).status, 422);
  assert.equal((await POST(new NextRequest('https://campus.test/api/session', { method: 'POST', headers: { origin: 'https://evil.test' } }))).status, 403);
  assert.equal((await POST(new NextRequest('https://campus.test/api/session', { method: 'POST', headers: { origin: 'https://campus.test' }, body: '{bad' }))).status, 422);
});
test('refresh rotates cookies and invalid refresh clears them', async () => {
  globalThis.fetch = async () => Response.json(session);
  assert.equal((await PATCH(request('PATCH', {}, 'cm_refresh=old'))).cookies.get('cm_refresh')?.value, 'refresh-new');
  globalThis.fetch = async () => Response.json({}, { status: 400 });
  const r = await PATCH(request('PATCH', {}, 'cm_refresh=old'));
  assert.equal(r.status, 401); assert.equal(r.cookies.get('cm_refresh')?.maxAge, 0);
});
test('provider outage retains session and is not misreported as wrong password', async () => {
  globalThis.fetch = async () => Response.json({}, { status: 503 });
  const r = await PATCH(request('PATCH', {}, 'cm_refresh=old'));
  assert.equal(r.status, 503); assert.equal(r.cookies.get('cm_refresh'), undefined);
});
test('middleware refreshes once for concurrent requests and forwards renewed cookie', async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls++; await new Promise(r => setTimeout(r, 5)); return Response.json(session); };
  const make = () => new NextRequest('https://campus.test/profile', { headers: { cookie: 'cm_access=expired; cm_refresh=old; cm_expires=1' } });
  const [a, b] = await Promise.all([proxy(make()), proxy(make())]);
  assert.equal(calls, 1); assert.equal(a.cookies.get('cm_access')?.value, 'access-new');
  assert.match(b.headers.get('x-middleware-request-cookie')!, /cm_access=access-new/);
});
test('logout revokes refresh session and clears local cookies', async () => {
  const urls: string[] = [];
  globalThis.fetch = async url => { urls.push(String(url)); return String(url).includes('logout') ? new Response(null, { status: 204 }) : Response.json(session); };
  const r = await DELETE(request('DELETE', undefined, 'cm_access=old; cm_refresh=refresh'));
  assert.equal((await r.json()).revoked, true); assert.equal(r.cookies.get('cm_access')?.maxAge, 0); assert.match(urls[1], /logout\?scope=local$/);
});
test('malformed provider session is rejected', async () => {
  globalThis.fetch = async () => Response.json({ access_token: 'partial' });
  assert.equal((await POST(request())).status, 503);
});

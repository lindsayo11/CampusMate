import { afterEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { NextRequest } from 'next/server';
import { sameOrigin } from '../lib/auth-session';
import { POST } from '../app/api/backend/[...path]/route';
const savedOrigin = process.env.APP_ORIGIN, savedFetch = globalThis.fetch;
afterEach(() => { if (savedOrigin === undefined) delete process.env.APP_ORIGIN; else process.env.APP_ORIGIN = savedOrigin; globalThis.fetch = savedFetch; });
function req(origin?: string) { return new NextRequest('http://localhost:3000/api/backend/v1/tools/tracker_write', {method:'POST', headers: origin ? {origin} : {}}); }
test('explicit browser origin works despite Next internal hostname mismatch', async () => {
 process.env.APP_ORIGIN='http://127.0.0.1:3000';
 globalThis.fetch = async () => Response.json({ok:true});
 assert.equal(sameOrigin(req('http://127.0.0.1:3000')), true);
 assert.equal((await POST(req('http://127.0.0.1:3000'), {params:Promise.resolve({path:['v1','tools','tracker_write']})})).status,200);
});
test('untrusted, missing, null, wrong-port and prefix origins reject with JSON', async () => {
 process.env.APP_ORIGIN='http://127.0.0.1:3000';
 globalThis.fetch = async () => { throw Error('must not forward'); };
 for (const origin of [undefined,'null','https://evil.test','http://127.0.0.1:3001','http://127.0.0.1:3000.evil.test','http://localhost:3000']) {
  const r=await POST(req(origin),{params:Promise.resolve({path:['v1','tools','tracker_write']})});
  assert.equal(r.status,403); assert.equal(typeof (await r.json()).detail,'string');
 }
});
test('without explicit origin only the request URL origin is allowed', () => {
 delete process.env.APP_ORIGIN;
 assert.equal(sameOrigin(req('http://localhost:3000')),true);
 assert.equal(sameOrigin(req('http://127.0.0.1:3000')),false);
});

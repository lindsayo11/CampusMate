import {test} from 'node:test';
import assert from 'node:assert/strict';
import {NextRequest} from 'next/server';
import {proxy} from '../proxy';
test('frozen enhancement pages return 404 while platform routes remain reachable',async()=>{
 delete process.env.ENABLE_AGENT_UI;delete process.env.ENABLE_COLLECTOR_UI;
 for(const path of ['/agent','/agent/nested','/admin/collector']){
  const r=await proxy(new NextRequest('https://campus.test'+path));assert.equal(r.status,404);assert.match(r.headers.get('x-middleware-rewrite')!,/_not-found$/);
 }
 assert.equal((await proxy(new NextRequest('https://campus.test/opportunities'))).status,200);
 process.env.ENABLE_AGENT_UI='true';assert.equal((await proxy(new NextRequest('https://campus.test/agent'))).status,200);delete process.env.ENABLE_AGENT_UI;
});

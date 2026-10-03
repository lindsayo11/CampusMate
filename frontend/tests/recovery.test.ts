import {beforeEach,afterEach,test} from 'node:test';
import assert from 'node:assert/strict';
import {NextRequest} from 'next/server';
import {POST,PATCH} from '../app/api/session/recovery/route';
const original=globalThis.fetch;
const session={access_token:'recovery-access',refresh_token:'secret-refresh',expires_in:600};
const valid={email:'student@example.edu',token:'123456',password:'new-password123'};
function req(method='PATCH',data:unknown=valid,origin='https://campus.test'){
 return new NextRequest('https://campus.test/api/session/recovery',{method,headers:{origin,cookie:'cm_access=unrelated-user'},body:JSON.stringify(data)});
}
beforeEach(()=>{process.env.SUPABASE_URL='https://auth.test';process.env.SUPABASE_ANON_KEY='test-public'});
afterEach(()=>{globalThis.fetch=original});
test('recovery request gives the same result for an unknown email',async()=>{
 globalThis.fetch=async(url,init)=>{assert.match(String(url),/recover$/);assert.equal(init?.method,'POST');return Response.json({})};
 const known=await (await POST(req('POST',{email:valid.email}))).json();
 globalThis.fetch=async()=>Response.json({error:'User not found'},{status:400});
 assert.deepEqual(await (await POST(req('POST',{email:valid.email}))).json(),known);
});
test('recovery input and cross-origin checks stop calls',async()=>{
 globalThis.fetch=async()=>{throw Error('must not call')};
 assert.equal((await PATCH(req('PATCH',valid,'https://evil.test'))).status,403);
 for(const value of [{...valid,token:'abc'},{...valid,password:'x'},{...valid,email:'bad'}])assert.equal((await PATCH(req('PATCH',value))).status,422);
});
test('verified recovery token updates password and revokes sessions without token leakage',async()=>{
 const calls:string[]=[];
 globalThis.fetch=async(url,init)=>{
  calls.push(String(url));const body=init?.body?JSON.parse(String(init.body)):undefined;
  if(String(url).endsWith('/verify')){assert.equal(body.type,'recovery');assert.equal(body.email,valid.email);return Response.json(session)}
  assert.equal((init?.headers as Record<string,string>).Authorization,'Bearer recovery-access');
  if(String(url).endsWith('/user')){assert.equal(init?.method,'PUT');assert.deepEqual(body,{password:valid.password});return Response.json({id:'user'})}
  return new Response(null,{status:204});
 };
 const r=await PATCH(req());assert.equal(r.status,200);assert.equal(r.cookies.get('cm_access')?.maxAge,0);
 const body=await r.text();assert.doesNotMatch(body,/recovery-access|secret-refresh/);assert.equal(JSON.parse(body).revoked,true);
 assert.match(calls[2],/logout\?scope=global$/);
});
test('expired OTP never updates password',async()=>{
 let calls=0;globalThis.fetch=async()=>{calls++;return Response.json({},{status:403})};
 assert.equal((await PATCH(req())).status,401);assert.equal(calls,1);
});
test('provider rate limits and outage are distinct',async()=>{
 for(const status of [429,503]){globalThis.fetch=async()=>Response.json({},{status});assert.equal((await POST(req('POST',{email:valid.email}))).status,status)}
});
test('password failure discards consumed recovery session and does not claim success',async()=>{
 const calls:string[]=[];
 globalThis.fetch=async(url)=>{calls.push(String(url));return String(url).endsWith('/verify')?Response.json(session):String(url).endsWith('/user')?Response.json({},{status:400}):new Response(null,{status:204})};
 const r=await PATCH(req());assert.equal(r.status,422);assert.equal(r.cookies.get('cm_access'),undefined);assert.match(calls[2],/scope=local$/);
});
test('revocation failure reports changed password with unconfirmed remote sessions',async()=>{
 globalThis.fetch=async(url)=>String(url).endsWith('/verify')?Response.json(session):String(url).endsWith('/user')?Response.json({}):Response.json({},{status:503});
 const r=await PATCH(req());assert.equal(r.status,200);assert.equal((await r.json()).revoked,false);
});

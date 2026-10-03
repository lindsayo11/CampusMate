import {NextRequest} from "next/server";
import {sameOrigin} from "@/lib/auth-session";
export const dynamic="force-dynamic";
async function proxy(req:NextRequest,{params}:{params:Promise<{path:string[]}>}){
 const {path}=await params;
 if(req.method!=="GET"&&!sameOrigin(req))return Response.json({detail:"请求来源不匹配，请检查 APP_ORIGIN 与浏览器地址"},{status:403});
 if(path.some(p=>p===".."||p==="."||p.includes("/")||p.includes("\\")))return Response.json({detail:"Invalid path"},{status:400});
 const target=(process.env.API_INTERNAL_URL||"http://127.0.0.1:8000")+"/"+path.map(encodeURIComponent).join("/")+req.nextUrl.search;
 const headers=new Headers();headers.set("Content-Type","application/json");
 const token=req.cookies.get("cm_access")?.value;
 const authorization=token?`Bearer ${token}`:req.headers.get("authorization");if(authorization)headers.set("Authorization",authorization);
 try {const upstream=await fetch(target,{method:req.method,headers,body:req.method==="GET"?undefined:await req.text(),cache:"no-store",redirect:"error",signal:AbortSignal.timeout(path[1]==='development-agent'?60000:path[1]==='startup'?35000:15000)});const responseHeaders=new Headers({"Content-Type":upstream.headers.get("Content-Type")||"application/json","Cache-Control":"private, no-store"});for(const name of ["Retry-After","X-Request-ID","Content-Disposition"]){const value=upstream.headers.get(name);if(value)responseHeaders.set(name,value)}return new Response(await upstream.text(),{status:upstream.status,headers:responseHeaders})}catch{return Response.json({detail:"API 暂不可用"},{status:502})}
}
export {proxy as GET,proxy as POST,proxy as PUT,proxy as PATCH,proxy as DELETE};

import "server-only";
import {cookies} from "next/headers";
import {redirect} from "next/navigation";
export async function privateApi(path:string){
 const token=(await cookies()).get("cm_access")?.value;
 const r=await fetch((process.env.API_INTERNAL_URL||"http://127.0.0.1:8000")+path,{cache:"no-store",signal:AbortSignal.timeout(15000),headers:token?{Authorization:`Bearer ${token}`}:{}});
 if(r.status===401)redirect("/login");
 if(!r.ok)throw new Error(r.status===403?"没有此页面的访问权限":"服务暂不可用");
 return r.json();
}

import "server-only";
import {cookies} from "next/headers";
import {cache} from "react";

// Shell requests never redirect: public pages and the login page stay reachable.
export const workspaceApi=cache(async (path:string)=>{
 const token=(await cookies()).get("cm_access")?.value;
 const response=await fetch((process.env.API_INTERNAL_URL||"http://127.0.0.1:8000")+path,{cache:"no-store",signal:AbortSignal.timeout(5000),headers:token?{Authorization:`Bearer ${token}`}:{}});
 if(!response.ok)throw new Error("暂时无法获取内容");
 return response.json();
});
export async function optionalWorkspaceApi(path:string){try{return await workspaceApi(path)}catch{return null}}

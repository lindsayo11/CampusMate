import {NextRequest,NextResponse} from "next/server";
import {AuthError,authFailure,authRequest,clearSession,parseSession,sameOrigin} from "@/lib/auth-session";
const genericMessage="如果该邮箱已注册且可以恢复，我们会发送验证码，请查看邮件。";
async function input(req:NextRequest){
 let data;
 try{data=await req.json()}catch{throw new AuthError(422,"输入无效")}
 if(!data||typeof data.email!=="string"||data.email.length>254||!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email))throw new AuthError(422,"请输入有效邮箱");
 return data;
}
export async function POST(req:NextRequest){
 if(!sameOrigin(req))return NextResponse.json({detail:"Invalid origin"},{status:403});
 try{
  const data=await input(req);
  try{await authRequest("recover",{email:data.email})}
  catch(error){
   // Never reveal whether an address exists. Do expose outages/rate limits for retry.
   if(!(error instanceof AuthError)||error.status!==401)throw error;
  }
  return NextResponse.json({ok:true,message:genericMessage},{headers:{"Cache-Control":"no-store"}});
 }catch(error){return authFailure(error)}
}
export async function PATCH(req:NextRequest){
 if(!sameOrigin(req))return NextResponse.json({detail:"Invalid origin"},{status:403});
 let token:string|undefined;
 try{
  const data=await input(req);
  if(typeof data.token!=="string"||!/^\d{6,10}$/.test(data.token)||typeof data.password!=="string"||data.password.length<8||data.password.length>1024)
   throw new AuthError(422,"请输入邮件中的验证码，新密码至少 8 位");
  // Use only a verified recovery session, never the normal browser session or a user ID.
  let verified;
  try{verified=await authRequest("verify",{email:data.email,token:data.token,type:"recovery"})}
  catch(error){if(error instanceof AuthError&&error.status===401)throw new AuthError(401,"验证码无效或已过期，请重新获取");throw error}
  token=parseSession(verified).access_token;
  try{await authRequest("user",{password:data.password},token,"PUT")}
  catch(error){
   if(error instanceof AuthError&&error.status===401)throw new AuthError(422,"新密码未被接受，请重新获取验证码并选择符合账号密码策略的密码");
   throw new AuthError(503,"密码更新结果未确认，请先尝试新密码登录，必要时重新获取验证码");
  }
  let revoked=true;
  try{await authRequest("logout?scope=global",undefined,token)}catch{revoked=false}
  token=undefined;
  const response=NextResponse.json({ok:true,revoked,message:revoked?"密码已更新，请使用新密码登录。":"密码已更新，但远端会话撤销未确认，请联系平台管理员检查其他登录会话。"});
  clearSession(response);
  return response;
 }catch(error){
  // If verification consumed an OTP but changing the password failed, discard that recovery session.
  if(token)try{await authRequest("logout?scope=local",undefined,token)}catch{}
  return authFailure(error);
 }
}

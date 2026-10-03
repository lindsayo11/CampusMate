export type Opportunity={id:string;type:string;title:string;organization:string;summary:string;location:string;deadline:string;source_url:string;source_label:string;trust_score:number;tags:string[];fetched_at:string};
export type OpportunityList={items:Opportunity[];total:number};
export type Profile={display_name:string;discoverable:boolean;user_id:string;school:string;college:string;grade:string;major:string;interests:string[];skills:string[];weekly_hours:number;degree:string;target_year:number|null;target_path:string;target_region:string;language_score:string;research_exp:string;internship_exp:string;competition_exp:string;startup_exp:string;updated_at:string};
export type DevelopmentPath={id:number;name:string;description:string;target_group:string;duration:string;status:string};
export type Plan={id:number;user_id:string;title:string;path_id:number|null;due_date:string|null;status:"todo"|"doing"|"done";note:string;created_at:string;updated_at:string};
export type TrackerItem={id:number;opportunity:Opportunity;stage:string;note:string;created_at:string;updated_at:string};
export type Eligibility={eligible:boolean|null;opportunity_id:string;results:{label:string;passed:boolean|null;evidence?:string;actual:string;expected:string;source_url:string}[]};
export type ReviewItem={id:number;title:string;source_url:string;risk_level:string;confidence:number;status:string;extracted_payload:string;created_at:string};
const base=typeof window === "undefined" ? (process.env.API_INTERNAL_URL||"http://127.0.0.1:8000") : "/api/backend";
export async function getOpportunities(type?:string,q?:string,status?:string):Promise<OpportunityList>{const u=new URL(`${base}/v1/opportunities`, typeof window === "undefined" ? undefined : window.location.origin);if(type)u.searchParams.set("type",type);if(q)u.searchParams.set("q",q);if(status)u.searchParams.set("status",status);try{const r=await fetch(u,{cache:"no-store"});if(!r.ok)throw new Error();return r.json()}catch{throw new Error("机会加载失败，请稍后重试")}}
export async function getOpportunity(id:string):Promise<Opportunity>{const r=await fetch(`${base}/v1/opportunities/${id}`,{cache:"no-store"});if(!r.ok)throw new Error("机会加载失败");return r.json()}
export async function getProfile():Promise<Profile>{const r=await fetch(`${base}/v1/profile`,{cache:"no-store"});if(!r.ok)throw new Error("画像读取失败");return r.json()}
export async function getPaths():Promise<DevelopmentPath[]>{const r=await fetch(`${base}/v1/paths`,{cache:"no-store"});if(!r.ok)throw new Error("路径读取失败");return r.json()}
export async function getPlans():Promise<Plan[]>{const r=await fetch(`${base}/v1/plans`,{cache:"no-store"});if(!r.ok)throw new Error("计划读取失败");return r.json()}
export async function getTracker():Promise<TrackerItem[]>{const r=await fetch(`${base}/v1/tracker/items`,{cache:"no-store"});if(!r.ok)throw new Error("加载失败，请稍后重试");return r.json()}
export async function getReviews():Promise<ReviewItem[]>{const r=await fetch(`${base}/v1/admin/reviews`,{cache:"no-store"});if(!r.ok)throw new Error("加载失败，请稍后重试");return r.json()}
export {base as apiBase};

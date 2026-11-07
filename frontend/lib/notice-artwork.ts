export type ArtworkTheme='competition'|'academic'|'study'|'overseas'|'career'|'public'|'venture'|'notice';
export function artworkTheme(paths:{code:string}[],title:string):ArtworkTheme{
  const codes=paths.map(p=>p.code).join(' ');
  if(/竞赛|大赛|挑战杯|建模|比赛/.test(title))return 'competition';
  if(/创业|创新|孵化/.test(title)||/entrepreneur|startup/.test(codes))return 'venture';
  if(/公务员|选调|事业单位|考公/.test(title)||/civil|public_institution/.test(codes))return 'public';
  if(/留学|境外|海外/.test(title)||/overseas/.test(codes))return 'overseas';
  if(/推免|保研|直博/.test(title)||/recommendation/.test(codes))return 'academic';
  if(/考研|研究生|考试/.test(title)||/postgraduate/.test(codes))return 'study';
  if(/就业|实习|招聘/.test(title)||/employment|job|intern/.test(codes))return 'career';
  return 'notice';
}
/** Local deterministic randomness: same record retains its artwork across SSR/refresh. */
export function artworkRecipe(id:string,title:string,paths:{code:string}[]){
  let seed=2166136261;
  for(const c of id+'|'+title+'|'+paths.map(p=>p.code).sort().join(','))seed=Math.imul(seed^c.charCodeAt(0),16777619)>>>0;
  const signature=seed.toString(16).padStart(8,'0');
  const next=()=>{seed=(seed+0x6d2b79f5)>>>0;let n=seed;n=Math.imul(n^n>>>15,n|1);n^=n+Math.imul(n^n>>>7,n|61);return ((n^n>>>14)>>>0)/4294967296};
  return {signature,theme:artworkTheme(paths,title),variant:Math.floor(next()*3),composition:Math.floor(next()*4),accent:Math.floor(next()*3),mainX:260+Math.round(next()*110),mainY:80+Math.round(next()*18),tilt:Math.round(next()*14)-7,sunX:55+Math.round(next()*440),sunY:24+Math.round(next()*28),sunR:22+Math.round(next()*22),hills:Array.from({length:6},()=>105+Math.round(next()*65)),details:Array.from({length:12},()=>Math.round(next()*100))};
}

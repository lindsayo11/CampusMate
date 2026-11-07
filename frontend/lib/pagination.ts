/** Keep all nine pages visible; compact larger catalogues without losing edges. */
export function pageNumbers(current:number,total:number):(number|'ellipsis')[]{
  total=Number.isFinite(total)?Math.max(0,Math.floor(total)):0;
  if(!total)return [];
  current=Number.isFinite(current)?Math.max(1,Math.min(total,Math.floor(current))):1;
  if(total<=9)return Array.from({length:total},(_,i)=>i+1);
  const start=Math.max(2,Math.min(current-2,total-5)),end=Math.min(total-1,Math.max(current+2,6));
  return [1,...(start>2?['ellipsis' as const]:[]),...Array.from({length:end-start+1},(_,i)=>start+i),...(end<total-1?['ellipsis' as const]:[]),total];
}

/* One-time, idempotent mechanical colour migration. Layouts and declarations
 * keep their cascade; values inherit the calendar palette only inside AppShell.
 * Existing var() fallbacks and public standalone/test rules remain untouched. */
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const postcss=require(path.join(root,'frontend/node_modules/postcss'));
const files=['app/globals.css','app/motion.css','app/phase2.css','app/startup/startup.css','components/assistant-studio.module.css','components/development-calendar.module.css','components/explore.module.css'];
const colorRE=/#(?:[\da-f]{8}|[\da-f]{6}|[\da-f]{4}|[\da-f]{3})\b|rgba?\([^)]*\)|\b(?:white|black)\b/gi;
const exactCalendar={
 '#fafaf7':'paper','#262e29':'ink','#606b62':'muted','#e0e4dd':'line','#3d5849':'accent',
 '#52775f':'focus','#ebf0e9':'accent-soft','#e2e8df':'line','#edf0e9':'surface-muted','#fff':'surface',
 '#2d4537':'accent-hover','#92a491':'line-strong','#e9eee6':'accent-soft','#e9d9b8':'warning-line',
 '#fcf7eb':'warning-soft','#715a2e':'warning-text','#49624f':'accent','#ae843a':'warning','#58738e':'info',
 '#cbd2c9':'line-strong','#f1f3ed':'surface-subtle','#f4f5f0':'paper','#eaf0e5':'selected',
 '#809a7c':'line-strong','#e2e9dd':'accent-soft','#dce4d9':'success-soft','#344d3a':'accent-text',
 '#eee3cc':'warning-bar','#70521b':'warning-text','#dce5ee':'info-soft','#36516a':'info-text',
 '#445c48':'accent','#7d847a':'faint','#eaf0e6':'accent-soft','#9b742b':'warning-text',
 '#8c9d86':'muted','#ccd3c9':'line-strong','#2f4335':'accent-hover','#d9e0d4':'line','#e8ece4':'surface-muted'
};
function rgb(value){
 const v=value.toLowerCase();if(v==='white')return [255,255,255,1];if(v==='black')return [0,0,0,1];
 if(v[0]==='#'){let h=v.slice(1);if(h.length<5)h=h.split('').map(x=>x+x).join('');return [parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16),h.length===8?parseInt(h.slice(6,8),16)/255:1]}
 const parts=v.match(/[\d.]+/g).map(Number);return [...parts.slice(0,3),parts[3]??1];
}
function tokenFor(raw,decl,file){
 const [r,g,b,a]=rgb(raw),selector=decl.parent.selector||'',prop=decl.prop;
 const max=Math.max(r,g,b)/255,min=Math.min(r,g,b)/255,light=(max+min)/2,sat=max===min?0:(max-min)/(1-Math.abs(2*light-1));
 if(/shadow/.test(prop))return `rgb(var(--cm-shadow-rgb) / ${Number(a.toFixed(3))})`;
 if(/backdrop|overlay/.test(selector)&&a<1&&/background/.test(prop))return `rgb(var(--cm-shadow-rgb) / ${Number(a.toFixed(3))})`;
 let token;
 const isText=/^(color|fill|stroke)$/.test(prop)||/--.*(ink|muted|accent|forest)/.test(prop);
 const isLine=/border|outline|--.*line/.test(prop),isBg=/background/.test(prop);
 const inverse=isText&&min>.96&&(file.includes('.module.css')||/primary|settings-avatar|user-avatar|topbar-avatar|toast|search button/.test(selector));
 if(inverse)token='inverse';
 else if(file.includes('development-calendar')&&exactCalendar[raw.toLowerCase()])token=exactCalendar[raw.toLowerCase()];
 else if(/--.*ink/.test(prop))token='ink';
 else if(/--.*muted/.test(prop))token='muted';
 else if(/--.*line/.test(prop))token='line';
 else if(/--.*(accent|forest)/.test(prop))token='accent';
 else if(/focus|outline/.test(prop)||/:focus/.test(selector)&&isLine)token='focus';
 else if(/danger|error|failed|\.fail\b|risk\.high/.test(selector))token=isText?'danger':isLine?'danger-line':'danger-soft';
 else if(/amber|warning|deadline|goldDot|starred|import-notice|\[role=.alert/.test(selector))token=isText?'warning-text':isLine?'warning-line':/Dot/.test(selector)?'warning':'warning-soft';
 else if(/success|passed|\.pass\b|\.green|\.saved/.test(selector))token=isText?'accent-text':isLine?'line':light<.65?'accent':'accent-soft';
 else if(isText){
  if(/muted|hint|meta|eyebrow|caption|small|note|placeholder|kicker/.test(selector))token='muted';
  else if(light<.24||light>.84||sat<.12)token=light>.35&&light<.75?'muted':'ink';
  else token=sat>.27?'accent':light>.35?'muted':'ink';
 }else if(isLine){token=light<.72?'line-strong':'line';}
 else if(isBg){
  if(/dot|marker|progress.*span|progress.*fill|progressFill|progressBar|isToday|\.toast|bar-fill|toggle.*checked|:checked/.test(selector)&&light<.86)token='accent';
  else if(min>.98)token='surface';
  else if(light>.965)token='paper';
  else if(light>.93)token='surface-subtle';
  else if(light>.80)token='accent-soft';
  else if(light<.35)token='surface';
  else token=sat>.25?'accent':'surface-muted';
 }else token='line';
 const ref=`var(--cm-${token}, ${raw})`;
 return a<1?`color-mix(in srgb, var(--cm-${token}, ${raw.startsWith('#')?raw.slice(0,7):'white'}) ${Number((a*100).toFixed(2))}%, transparent)`:ref;
}
function migrate(value,decl,file){
 // Protect complete var() expressions, including fallback literals, on reruns.
 let out='',offset=0;const re=/var\(/g;let m;
 const colors=s=>s.replace(colorRE,raw=>tokenFor(raw,decl,file));
 while((m=re.exec(value))){out+=colors(value.slice(offset,m.index));let depth=1,i=m.index+4;while(i<value.length&&depth){if(value[i]==='(')depth++;else if(value[i]===')')depth--;i++}out+=value.slice(m.index,i);offset=i;re.lastIndex=i}
 return out+colors(value.slice(offset));
}
const audit=[];
for(const file of files){
 const full=path.join(root,'frontend',file),original=fs.readFileSync(full,'utf8'),tree=postcss.parse(original);let changed=0;
 if(file==='app/globals.css')tree.walkRules(rule=>{
  // This obsolete panel no longer exists. Keep sibling overview/direction rules.
  const kept=rule.selectors.filter(s=>s.trim()&&! /\.console-(schedule|calendar|timeline|event)(?:[-\s.:>#[]|$)/.test(s));
  if(!kept.length)rule.remove();else rule.selectors=kept;
 });
 // These end-of-file themes only imposed obsolete black/white colours.
 if(file==='app/startup/startup.css'||file==='app/phase2.css'){
  let obsolete=false;for(const n of [...tree.nodes]){if(n.type==='comment'&&/strictly black|Keep phase-two/.test(n.text))obsolete=true;if(obsolete)n.remove();}
 }
 tree.walkDecls(decl=>{
  const selector=decl.parent.selector||'';
  if(/:root|\.test-/.test(selector))return;
  if(!/color|background|border|outline|shadow|fill|stroke|^--/.test(decl.prop))return;
  const next=migrate(decl.value,decl,file);if(next!==decl.value){changed++;decl.value=next}
 });
 const next=tree.toString();if(next!==original)fs.writeFileSync(full,next);
 audit.push({file,declarationsMigrated:changed});
}
console.log(JSON.stringify(audit,null,2));

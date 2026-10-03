"""Read-only cloud collection dashboard; private application routes remain authenticated."""
from fastapi import APIRouter,Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .intake_models import CollectionAlert
router=APIRouter()


@router.get('/v1/data/collection-alerts')
def active_alerts(db:Session=Depends(get_db)):
    # Monitor-authored public operational summaries only; no raw failed responses.
    return {'items':[{'message':a.message,'first_seen_at':a.first_seen_at,'last_seen_at':a.last_seen_at}
        for a in db.scalars(select(CollectionAlert).where(CollectionAlert.status=='active')
            .order_by(CollectionAlert.first_seen_at.desc()).limit(100)).all()]}


@router.get('/collection',response_class=HTMLResponse)
def dashboard():
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CampusMate · 持续采集</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f6f4;color:#203e38;font:16px/1.7 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:32px 24px}.brand{font-weight:750;letter-spacing:.04em;color:#43756a}h1{font-size:34px;margin-bottom:8px}p{color:#5f726c}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card,section{background:white;padding:24px;border:1px solid #dce5e0;border-radius:16px;margin:20px 0}.card strong{font-size:36px;color:#38685b}table{border-collapse:collapse;width:100%}td,th{padding:12px;text-align:left;border-bottom:1px solid #e8eeea}.table{overflow:auto}a{color:#38685b}.row{border-bottom:1px solid #e8eeea;padding:14px 0}.row small{display:block;color:#72827c}@media(max-width:700px){.cards{grid-template-columns:1fr}.card{margin:0}h1{font-size:28px}main{padding:24px 16px}}
</style><main><div class="brand">CampusMate 校伴 · 官方信息</div><h1>持续采集与覆盖</h1><p>查看采集状态和最新收录。申请窗口依据官方明示日期，资格与材料要求请核对原文。</p><div class="cards"><div class="card"><strong id="sources">—</strong><p>有内容的来源</p></div><div class="card"><strong id="items">—</strong><p>公开收录条目 · 含历史资料</p></div><div class="card"><strong id="rate">—</strong><p>近 24 小时成功检查比例</p></div></div><section><h2>运行与质量</h2><p id="health">正在读取最新状态…</p><p id="dates"></p><p id="sync"></p><div class="table"><table><thead><tr><th>领域</th><th>启用／正常</th><th>公开条目</th><th>窗口内／尚未开始</th></tr></thead><tbody id="topics"></tbody></table></div></section><section><h2>需要处理的告警</h2><p>来源检查超时、连续失败和采集心跳异常；恢复后自动解除。</p><div id="alerts">正在读取…</div></section><section><h2>最近收录</h2><p>已对原文、标题和日期均一致的同文合并展示，保留官方出处。</p><div id="recent"></div></section><small id="updated"></small></main><script>
const node=id=>document.getElementById(id);async function load(){try{const response=await fetch('/v1/data/coverage');if(!response.ok)throw Error();const d=await response.json(),q=d.quality;node('sources').textContent=d.sources_with_content;node('items').textContent=d.sources.reduce((n,s)=>n+s.items,0);node('rate').textContent=q.attempt_success_rate_24h==null?'暂无记录':q.attempt_success_rate_24h+'%';node('health').textContent='采集 Worker：'+(q.worker.status==='ok'?'正常':'需检查')+' · 独立告警监测：'+(q.monitor_status==='ok'?'正常':'需检查')+' · 当前告警 '+q.active_alerts+' 项 · 未成功检查或已超时来源 '+q.unsuccessful_sources+' 个';node('dates').textContent='截止日期完整度 '+q.deadline_completeness+'% · 已知窗口内 '+(q.availability.open||0)+' · 尚未开始 '+(q.availability.upcoming||0)+' · 日期待确认 '+(q.availability.needs_confirmation||0);if(q.sync&&q.sync.state!=='not_configured'){node('sync').textContent='官方原文同步：'+({ok:'正常',running:'正在同步',partial:'部分内容等待重试',error:'连接异常',stale:'检查超时',pending:'等待首次同步'}[q.sync.state]||'待检查')+' · 累计接收 '+q.sync.pulled+' 条 · 最近完成 '+(q.sync.last_success_at?new Date(q.sync.last_success_at).toLocaleString('zh-CN'):'暂无记录')+'；接收后重新解析，不计为本站成功访问官网。'}node('topics').replaceChildren();for(const t of q.topics){const tr=document.createElement('tr');for(const value of [t.label,t.enabled_sources+'／'+t.healthy_sources,t.public_items,t.open+'／'+t.upcoming]){const td=document.createElement('td');td.textContent=value;tr.append(td)}node('topics').append(tr)}const r=await fetch('/v1/data/catalog?limit=10');if(r.ok){const catalog=await r.json();node('recent').replaceChildren();for(const item of catalog.items){const div=document.createElement('div');div.className='row';const a=document.createElement('a');a.textContent=item.title;a.href=item.document.canonical_url;a.target='_blank';a.rel='noreferrer';const small=document.createElement('small');small.textContent=item.source.name+' · 截止时间 '+(item.deadline||'以原文为准');div.append(a,small);node('recent').append(div)}}const ar=await fetch('/v1/data/collection-alerts');if(ar.ok){const ad=await ar.json();node('alerts').replaceChildren();if(!ad.items.length)node('alerts').textContent='当前没有活动告警';for(const alert of ad.items){const line=document.createElement('div');line.className='row';line.textContent=alert.message;node('alerts').append(line)}}node('updated').textContent='最近读取：'+new Date().toLocaleString('zh-CN')}catch(error){node('health').textContent='当前暂时无法读取采集状态，请稍后刷新'}}load();setInterval(load,60000);
</script></html>'''

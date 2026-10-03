"""Portable, isolated local preview configuration for a local checkout."""
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def prepare(api_port=8000, web_port=3000, force=False):
    snapshot = ROOT / 'demo-data/release-preview.db'
    if not snapshot.is_file():
        raise RuntimeError('缺少 demo-data/release-preview.db；请先运行 scripts/export_demo_data.py 从你的数据库导出公开快照')
    data = ROOT / 'local-data/demo.db'
    data.parent.mkdir(exist_ok=True)
    if not data.exists():
        with sqlite3.connect(snapshot.as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(data) as dest:
            src.backup(dest)
    manifest = json.loads((ROOT/'backend/app/postgraduate_sources.json').read_text(encoding='utf-8'))
    hosts = sorted({urlsplit(url).hostname for source in manifest['sources'] for url in source['index_urls']})
    env = {'DATABASE_URL':'sqlite:///'+data.as_posix(),'DEMO_MODE':'true',
        'ADMIN_USER_IDS':'demo-user','COLLECTOR_ENABLED':'false',
        'PUBLIC_NOTICE_WATCH_ENABLED':'true','COLLECTOR_ALLOWED_HOSTS':','.join(hosts),
        'COLLECTOR_SKIP_ROBOTS':'false','COLLECTOR_ALLOW_PLAINTEXT_HOSTS':'',
        'SINGLE_ADMIN_OVERRIDES':'false','ENABLE_AGENT_UI':'true','ENABLE_COLLECTOR_UI':'false',
        'API_INTERNAL_URL':f'http://127.0.0.1:{api_port}',
        'APP_ORIGIN':f'http://127.0.0.1:{web_port}',
        'CORS_ORIGINS':f'http://127.0.0.1:{web_port}','PORT':str(web_port),
        'WEB_HOST':'127.0.0.1','NO_PROXY':'127.0.0.1,localhost',
        'no_proxy':'127.0.0.1,localhost','DIFY_API_BASE':'','DIFY_APP_KEY':'',
        'DEVELOPMENT_DIFY_API_BASE':'','DEVELOPMENT_DIFY_APP_KEY':'',
        'SUPABASE_URL':'','SUPABASE_ANON_KEY':''}
    # Quote values so paths containing spaces work with dotenv readers too.
    body = '# 本地演示配置；禁止用于公网部署\n'+''.join(
        key+'='+json.dumps(value,ensure_ascii=False)+'\n' for key,value in env.items())
    for path in [ROOT/'.env',ROOT/'backend/.env',ROOT/'frontend/.env.local']:
        if force or not path.exists():
            path.write_text(body,encoding='utf-8')
            path.chmod(0o600)
    return env

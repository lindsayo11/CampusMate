"""Run the browser acceptance suite with isolated admin/student demo services.
Requires an installed Chromium (CHROMIUM_PATH) and `npm run build` beforehand.
No writes are made to the retained demo database. Four child processes share
one local network namespace; all are stopped on success or failure.
"""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
runtime=ROOT/'.test-runtime/ui33'
runtime.mkdir(parents=True,exist_ok=True)
db=runtime/('preview.db' if '--screenshots-only' in sys.argv else 'acceptance.db')
if not db.exists():
    with sqlite3.connect(ROOT/'demo-data/retained-demo.db') as src,sqlite3.connect(db) as dst:
        src.backup(dst)
base={**os.environ,'PYTHONPATH':str(ROOT/'backend'),'DATABASE_URL':'sqlite:///'+str(db),
      'DEMO_MODE':'true','COLLECTOR_ENABLED':'false','ENABLE_AGENT_UI':'true',
      'E2E_BASE_URL':'http://127.0.0.1:3033','E2E_API_URL':'http://127.0.0.1:8033',
      'E2E_STUDENT_URL':'http://127.0.0.1:3034','E2E_AGENT_UI':'true'}
processes=[]
def start(command,env,label):
    f=open(runtime/(label+'.log'),'w')
    p=subprocess.Popen(command,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
    processes.append((p,f))
def ready(url):
    for _ in range(100):
        try:
            with urllib.request.urlopen(url,timeout=3) as r:
                if r.status==200:return
        except Exception:pass
        if any(p.poll() is not None for p,_ in processes):raise RuntimeError('A service exited; inspect .test-runtime/ui33 logs')
        time.sleep(.2)
    raise RuntimeError('Service startup timed out: '+url)
try:
    for apiport,webport,admins in [(8033,3033,'demo-user'),(8034,3034,'reserved-administrator')]:
        env={**base,'ADMIN_USER_IDS':admins,'API_INTERNAL_URL':f'http://127.0.0.1:{apiport}',
             'APP_ORIGIN':f'http://127.0.0.1:{webport}','PORT':str(webport)}
        start([str(ROOT/'backend/.venv/bin/python'),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(apiport)],env,f'api-{apiport}')
        ready(f'http://127.0.0.1:{apiport}/health')
        start(['node','scripts/start-web.cjs'],env,f'web-{webport}')
        ready(f'http://127.0.0.1:{webport}/')
    if '--screenshots-only' not in sys.argv:
        tests=[x for x in sys.argv[1:] if not x.startswith('--')] or ['e2e/workspace.spec.ts','e2e/collaboration.spec.ts','e2e/data.spec.ts','e2e/golden.spec.ts']
        subprocess.run(['npx','playwright','test',*tests,*(['--grep',os.environ['E2E_GREP']] if os.environ.get('E2E_GREP') else []),'--reporter=line'],cwd=ROOT/'frontend',env=base,check=True)
    subprocess.run(['node','scripts/capture-ui.cjs'],cwd=ROOT,env=base,check=True)
finally:
    for p,_ in reversed(processes):p.terminate()
    for p,f in processes:
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:p.kill();p.wait()
        f.close()

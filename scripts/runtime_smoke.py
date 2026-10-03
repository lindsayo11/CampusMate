"""Cold-start API, Web and Worker on an isolated SQLite database; verify restore.
Run with backend/.venv/bin/python after npm run build. Does not replace browser E2E.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def counts(path):
    with sqlite3.connect(path) as db:
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: db.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0] for name in names}


def main():
    runtime = ROOT / '.test-runtime'
    runtime.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=runtime, prefix='smoke-') as tmp:
        db = Path(tmp)/'source.db'
        env = {**os.environ, 'DATABASE_URL': 'sqlite:///'+str(db), 'DEMO_MODE': 'true',
               'ADMIN_USER_IDS': 'demo-user', 'COLLECTOR_ENABLED': 'false', 'PUBLIC_NOTICE_WATCH_ENABLED':'false',
               'ENABLE_AGENT_UI': os.environ.get('SMOKE_AGENT_UI','false'), 'ENABLE_COLLECTOR_UI': 'false',
               'API_INTERNAL_URL': 'http://127.0.0.1:18080', 'APP_ORIGIN': 'http://127.0.0.1:13000',
               'PORT': '13000', 'NO_PROXY': '127.0.0.1,localhost', 'no_proxy': '127.0.0.1,localhost'}
        def run(*args, cwd=ROOT):
            return subprocess.run(args, cwd=cwd, env=env, check=True, capture_output=True, text=True)
        run(sys.executable,'-m','alembic','-c','backend/alembic.ini','upgrade','head')
        run(sys.executable,'-m','alembic','-c','backend/alembic.ini','check')
        processes=[]
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def get(url):
            try:
                with opener.open(url,timeout=10) as r:return r.status,r.read().decode()
            except urllib.error.HTTPError as e:return e.code,e.read().decode()
        def wait(url,p):
            for _ in range(80):
                if p.poll() is not None: raise RuntimeError('Server exited, see .test-runtime/runtime-smoke.log')
                try:
                    if get(url)[0]==200:return
                except OSError:pass
                time.sleep(.25)
            raise RuntimeError('Server startup timed out')
        with (runtime/'runtime-smoke.log').open('w') as log:
            try:
                api=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','18080'],cwd=ROOT/'backend',env=env,stdout=log,stderr=log);processes.append(api)
                wait(env['API_INTERNAL_URL']+'/health/ready',api)
                worker=subprocess.Popen([sys.executable,'-m','app.worker'],cwd=ROOT/'backend',env=env,stdout=log,stderr=log);processes.append(worker)
                web=subprocess.Popen(['node','../scripts/start-web.cjs'],cwd=ROOT/'frontend',env=env,stdout=log,stderr=log);processes.append(web)
                wait(env['APP_ORIGIN']+'/login',web)
                def write(origin):
                    request = urllib.request.Request(env['APP_ORIGIN'] + '/api/backend/v1/tools/tracker_write',
                        data=json.dumps({'opportunity_id': 'job-001', 'stage': 'saved', 'note': 'origin regression'}).encode(),
                        headers={'Origin': origin, 'Content-Type': 'application/json'}, method='POST')
                    try:
                        with opener.open(request, timeout=15) as response:
                            return response.status, json.load(response)
                    except urllib.error.HTTPError as exc:
                        return exc.code, json.load(exc)
                status, result = write(env['APP_ORIGIN'])
                assert status == 200 and result['stage'] == 'saved', (status, result)
                status, result = write('https://evil.test')
                assert status == 403 and isinstance(result['detail'], str), (status, result)
                pages={}
                for path in ['/','/opportunities','/opportunity/job-001','/profile','/eligibility','/tracker','/notifications','/teams','/team-manager','/safety','/login','/recover','/admin','/admin/audit','/admin/review','/admin/reports','/admin/sources','/admin/operations','/data','/data/timeline','/admin/data','/admin/registry','/admin/entrepreneurship','/admin/overseas']:
                    status,html=get(env['APP_ORIGIN']+path)
                    assert status==200 and '暂时无法打开此页面</h1>' not in html,(path,status)
                    pages[path]=status
                if env['ENABLE_AGENT_UI']=='true':
                    status,html=get(env['APP_ORIGIN']+'/agent')
                    assert status==200 and '和校伴，一起想清楚下一步' in html
                    pages['/agent']=status
                for path in (['/agent'] if env['ENABLE_AGENT_UI']!='true' else [])+['/admin/collector','/opportunity/does-not-exist']:
                    status,html=get(env['APP_ORIGIN']+path)
                    assert '页面或机会不存在' in html,path
                    pages[path]={'http_status':status,'not_found_content':True}
                status,body=get(env['API_INTERNAL_URL']+'/v1/admin/operations')
                assert json.loads(body)['worker']['healthy'],body
                assert worker.poll() is None
                assert get(env['API_INTERNAL_URL']+'/health/live')[0]==200
                # Add an actually due reminder and run the production cycle, twice.
                with sqlite3.connect(db) as con:
                    con.execute("INSERT INTO reminders(user_id,opportunity_id,due_at,sent,created_at,channel) VALUES ('smoke-user','job-001','2020-01-01',0,'2020-01-01','in_app')")
                run(sys.executable,'-c','from app.worker import run_cycle;run_cycle();run_cycle()',cwd=ROOT/'backend')
                with sqlite3.connect(db) as con:
                    assert con.execute("SELECT count(*) FROM notifications WHERE user_id='smoke-user'").fetchone()[0]==1
                # Stop all writers before comparing backup and restored data.
                for p in reversed(processes):p.terminate();p.wait(timeout=10)
                archive=Path(tmp)/'backup.sqlite';restored=Path(tmp)/'restored.db'
                run(sys.executable,'scripts/backup.py','backup',str(archive))
                env['DATABASE_URL']='sqlite:///'+str(restored)
                run(sys.executable,'scripts/backup.py','restore',str(archive))
                assert counts(db)==counts(restored)
                result={'status':'passed','pages':pages,'worker':'healthy; due reminder exactly once','backup_restore_table_counts':counts(restored),'browser_e2e':'not covered by HTTP smoke'}
                (runtime/'runtime-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
                print(json.dumps(result,ensure_ascii=False))
            finally:
                for p in reversed(processes):
                    if p.poll() is None:
                        p.terminate()
                        try:p.wait(timeout=10)
                        except subprocess.TimeoutExpired:p.kill();p.wait()


if __name__=='__main__':main()

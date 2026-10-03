"""Run Agent browser acceptance against isolated API/Web processes and database.
Requires a frontend production build. Set CHROMIUM_PATH for a custom browser.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from e2e import ready

ROOT=Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='campusmate-agent-ui-') as tmp:
        env={**os.environ,'DATABASE_URL':f'sqlite:///{tmp}/test.db','DEMO_MODE':'true',
            'ADMIN_USER_IDS':'demo-user','API_INTERNAL_URL':'http://127.0.0.1:8035',
            'PORT':'3035','APP_ORIGIN':'http://127.0.0.1:3035','WEB_HOST':'127.0.0.1',
            'CORS_ORIGINS':'http://127.0.0.1:3035','SUPABASE_URL':'','SUPABASE_ANON_KEY':'',
            'DIFY_API_BASE':'','DIFY_APP_KEY':'','DEVELOPMENT_DIFY_API_BASE':'',
            'DEVELOPMENT_DIFY_APP_KEY':'','COLLECTOR_ENABLED':'false',
            'PUBLIC_NOTICE_WATCH_ENABLED':'false','ENABLE_AGENT_UI':'true',
            'E2E_BASE_URL':'http://127.0.0.1:3035','E2E_API_URL':'http://127.0.0.1:8035',
            'NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost'}
        subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','upgrade','head'],cwd=ROOT,env=env,check=True)
        children=[]
        with open(Path(tmp)/'servers.log','w+') as log:
            try:
                api=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8035'],cwd=ROOT/'backend',env=env,stdout=log,stderr=log)
                children.append(api);ready(env['API_INTERNAL_URL']+'/health/ready',api)
                web=subprocess.Popen(['node','../scripts/start-web.cjs'],cwd=ROOT/'frontend',env=env,stdout=log,stderr=log)
                children.append(web);ready(env['APP_ORIGIN']+'/agent',web)
                selection=sys.argv[1:] or ['agent-enhancements.spec.ts','startup.spec.ts','workspace.spec.ts','--grep','助手准备清单|助手：|创业工作台']
                result=subprocess.run(['npm','run','test:e2e','--',*selection],cwd=ROOT/'frontend',env=env)
                if result.returncode:
                    log.seek(0);print(log.read()[-6000:])
                return result.returncode
            finally:
                for child in reversed(children):
                    child.terminate()
                    try:child.wait(timeout=5)
                    except subprocess.TimeoutExpired:child.kill();child.wait()


if __name__=='__main__':sys.exit(main())

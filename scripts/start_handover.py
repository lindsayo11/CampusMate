"""Start the packaged local preview on macOS, Linux or Windows.
Install Python dependencies and run npm ci / npm run build first.
"""
import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from handover_env import ROOT, prepare


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-port',type=int,default=8000)
    parser.add_argument('--web-port',type=int,default=3000)
    parser.add_argument('--collector-off',action='store_true',help='本地演示不请求外部高校网站')
    args=parser.parse_args()
    if not all(1024<=p<=65535 for p in [args.api_port,args.web_port]) or args.api_port==args.web_port:
        parser.error('使用两个不同的 1024–65535 端口')
    node=shutil.which('node')
    if not node or not (ROOT/'frontend/.next/standalone/server.js').is_file():
        parser.error('请先安装 Node.js，并在 frontend 运行 npm ci 和 npm run build')
    for port in [args.api_port,args.web_port]:
        try:
            with socket.socket() as probe:probe.bind(('127.0.0.1',port))
        except OSError:
            parser.error(f'端口 {port} 已被占用，请指定其他 --api-port / --web-port')
    env={**os.environ,**prepare(args.api_port,args.web_port)}
    if args.collector_off:
        env['PUBLIC_NOTICE_WATCH_ENABLED']='false'
    subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=ROOT/'backend',env=env,check=True)
    subprocess.run([sys.executable, str(ROOT/'scripts/refresh_postgraduate.py'), '--install'],
                   cwd=ROOT/'backend', env=env, check=True)
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    children=[]
    def start(cmd,cwd):
        options={'start_new_session':True} if os.name!='nt' else {'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP}
        p=subprocess.Popen(cmd,cwd=cwd,env=env,**options);children.append(p);return p
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:
        api=start([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1',
                   '--port',str(args.api_port)],ROOT/'backend')
        for _ in range(60):
            if api.poll() is not None:
                raise RuntimeError('API 启动失败；检查端口和上方日志')
            try:
                with opener.open(env['API_INTERNAL_URL']+'/health/ready',timeout=1) as r:
                    if r.status==200:break
            except OSError:time.sleep(.25)
        else:raise RuntimeError('API 启动超时')
        start([sys.executable,'-m','app.worker'],ROOT/'backend')
        start([node,'../scripts/start-web.cjs'],ROOT/'frontend')
        print('\nCampusMate 交接演示：'+env['APP_ORIGIN'],flush=True)
        print('持续采集：'+('关闭' if args.collector_off else '开启')+'；Ctrl+C 停止三个服务。',flush=True)
        while True:
            if any(p.poll() is not None for p in children):
                raise RuntimeError('一个服务退出，已停止整组服务；查看上方日志后重新启动')
            time.sleep(.25)
    except KeyboardInterrupt:
        return 0
    finally:
        for p in children:
            if p.poll() is None:
                try:
                    if os.name=='nt':p.send_signal(signal.CTRL_BREAK_EVENT)
                    else:os.killpg(p.pid,signal.SIGTERM)
                except (OSError,ValueError):p.terminate()
        for p in children:
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill();p.wait()


if __name__=='__main__':sys.exit(main())

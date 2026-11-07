"""Run demo browser checks with isolated DB and supervised API/Web processes."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def ready(url, process):
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError(f"Server exited: {url}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(.25)
    raise RuntimeError(f"Server not ready: {url}")


def main():
    api_port = os.environ.get("E2E_API_PORT", "8000")
    web_port = os.environ.get("E2E_WEB_PORT", "3000")
    with tempfile.TemporaryDirectory(prefix="campusmate-e2e-") as tmp:
        env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp}/test.db", "DEMO_MODE": "true",
               "ADMIN_USER_IDS": "demo-user", "API_INTERNAL_URL": f"http://127.0.0.1:{api_port}", "E2E_API_URL": f"http://127.0.0.1:{api_port}",
               "PORT": web_port, "APP_ORIGIN": f"http://127.0.0.1:{web_port}", "E2E_BASE_URL": f"http://127.0.0.1:{web_port}", "SUPABASE_URL": "", "SUPABASE_ANON_KEY": "", "DIFY_API_BASE": "", "DIFY_APP_KEY": "", "COLLECTOR_ENABLED": "false", "ENABLE_AGENT_UI": "false", "ENABLE_COLLECTOR_UI": "false"}
        subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"], cwd=ROOT, env=env, check=True)
        processes = []
        try:
            with open(Path(tmp) / "servers.log", "w+") as log:
                api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", api_port], cwd=ROOT / "backend", env=env, stdout=log, stderr=log)
                processes.append(api)
                ready(f"http://127.0.0.1:{api_port}/health/ready", api)
                web = subprocess.Popen(["node", "../scripts/start-web.cjs"], cwd=ROOT / "frontend", env=env, stdout=log, stderr=log)
                processes.append(web)
                ready(f"http://127.0.0.1:{web_port}/login", web)
                result = subprocess.run(["npm", "run", "test:e2e", "--", *sys.argv[1:]], cwd=ROOT / "frontend", env=env)
                if result.returncode:
                    log.seek(0)
                    print(log.read()[-8000:])
                return result.returncode
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    sys.exit(main())

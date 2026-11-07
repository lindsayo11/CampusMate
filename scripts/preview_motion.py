"""Run an isolated, loopback-only UI preview, optionally with real AI.

Usage: backend/.venv/Scripts/python.exe scripts/preview_motion.py
"""
import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

from local_env import ROOT, prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=8001)
    parser.add_argument("--web-port", type=int, default=3000)
    parser.add_argument("--production", action="store_true", help="Serve the verified production build.")
    parser.add_argument("--with-ai", action="store_true", help="Use AI credentials from the process environment; keep the database and auth local.")
    args = parser.parse_args()
    if args.api_port == args.web_port or not all(1024 <= port <= 65535 for port in (args.api_port, args.web_port)):
        parser.error("Choose two different ports between 1024 and 65535.")
    node = shutil.which("node")
    if not node:
        parser.error("Node.js is required.")
    for port in (args.api_port, args.web_port):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                parser.error(f"Port {port} is in use; existing services will not be stopped.")
    env = {**os.environ, **prepare(args.api_port, args.web_port)}
    env.update({
        "PUBLIC_NOTICE_WATCH_ENABLED": "false",
        "COLLECTOR_ENABLED": "false",
        "JEV_API_KEY": "",
        "NEXT_TELEMETRY_DISABLED": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    if args.with_ai:
        if not env.get("DEEPSEEK_API_KEY", "").strip():
            parser.error("--with-ai requires DEEPSEEK_API_KEY in the process environment. Never pass it on the command line.")
    else:
        env.update({"DEEPSEEK_API_KEY": "", "TAVILY_API_KEY": ""})
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=ROOT / "backend", env=env, check=True)
    processes = []
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        api = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.api_port)],
            cwd=ROOT / "backend", env=env)
        processes.append(api)
        for _ in range(120):
            if api.poll() is not None:
                raise RuntimeError("Local API exited; inspect the preview log.")
            try:
                with opener.open(env["API_INTERNAL_URL"] + "/health/ready", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.25)
        else:
            raise RuntimeError("Local API did not become ready.")
        # Invoke Node directly: npm .cmd shims misparse '&' in this checkout's path.
        command = ([node, str(ROOT / "scripts/start-web.cjs")] if args.production else
                   [node, str(ROOT / "frontend/node_modules/next/dist/bin/next"), "dev",
                    "--hostname", "127.0.0.1", "--port", str(args.web_port)])
        web_env = {key: value for key, value in env.items()
                   if key not in {"DEEPSEEK_API_KEY", "TAVILY_API_KEY", "JEV_API_KEY"}}
        web = subprocess.Popen(command, cwd=ROOT / "frontend", env=web_env)
        processes.append(web)
        print(f"Local UI preview: {env['APP_ORIGIN']}/console", flush=True)
        print("Local demo database; collectors disabled; AI " + ("enabled." if args.with_ai else "disabled."), flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(.5)
        raise RuntimeError("A preview service exited; stopping its companion.")
    except KeyboardInterrupt:
        return 0
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    sys.exit(main())

"""Bounded development restarts and process-group cleanup (POSIX)."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    commands = {
        'API': ([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], ROOT / 'backend'),
        'Worker': ([sys.executable, '-m', 'app.worker'], ROOT / 'backend'),
        'Web': (['npm', 'run', 'dev', '--', '--hostname', '127.0.0.1', '--port', os.getenv('PORT', '3000')], ROOT / 'frontend'),
    }
    children, restarts = {}, dict.fromkeys(commands, 0)
    def stop(*_):
        raise KeyboardInterrupt
    def kill_group(p, sig):
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            pass
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while True:
            for name, (cmd, cwd) in commands.items():
                p = children.get(name)
                if p is not None and p.poll() is None:
                    continue
                if p is not None:
                    kill_group(p, signal.SIGKILL)
                    if restarts[name] >= 3:
                        print(f'{name} exited ({p.returncode}); restart budget exhausted, stopping all services', file=sys.stderr, flush=True)
                        return 1
                    restarts[name] += 1
                    print(f'{name} exited ({p.returncode}); restart {restarts[name]}/3', file=sys.stderr, flush=True)
                    time.sleep(1)
                children[name] = subprocess.Popen(cmd, cwd=cwd, start_new_session=True)
            time.sleep(.25)
    except KeyboardInterrupt:
        return 0
    finally:
        for p in children.values():
            kill_group(p, signal.SIGTERM)
        deadline = time.monotonic() + 5
        while any(p.poll() is None for p in children.values()) and time.monotonic() < deadline:
            time.sleep(.1)
        for p in children.values():
            kill_group(p, signal.SIGKILL)
            p.wait()


if __name__ == '__main__':
    sys.exit(main())

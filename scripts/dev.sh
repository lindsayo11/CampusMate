#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x backend/.venv/bin/python ]; then
  python3 -m venv backend/.venv
fi
backend/.venv/bin/python -m pip install -c backend/requirements-tested.txt -e './backend[dev]'
(cd frontend && npm ci)
backend/.venv/bin/python scripts/doctor.py
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
export API_INTERNAL_URL=http://127.0.0.1:8000
export PORT="${PORT:-3000}"
export APP_ORIGIN="${APP_ORIGIN:-http://127.0.0.1:$PORT}"
echo "CampusMate: $APP_ORIGIN (浏览器地址须与 APP_ORIGIN 一致)"
exec backend/.venv/bin/python scripts/dev_supervisor.py

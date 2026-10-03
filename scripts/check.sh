#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .test-runtime
test_dir=$(mktemp -d "$PWD/.test-runtime/check.XXXXXX")
trap 'rm -rf "$test_dir"' EXIT
export DATABASE_URL="sqlite:///$test_dir/test.db"
export DEMO_MODE=true
export ADMIN_USER_IDS=demo-user
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/python scripts/test_dev_supervisor.py
cd frontend
npm test
npm run typecheck
if [[ -f ../scripts/restricted-node.cjs ]]; then
  NODE_OPTIONS="--require=$PWD/../scripts/restricted-node.cjs${NODE_OPTIONS:+ $NODE_OPTIONS}" npm run build
else
  npm run build
fi

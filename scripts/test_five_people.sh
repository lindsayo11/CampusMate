#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .test-runtime
run_dir=$(mktemp -d "$PWD/.test-runtime/five-people.XXXXXX")
export DATABASE_URL="sqlite:///$run_dir/test.db"
export DEMO_MODE=true
export ADMIN_USER_IDS=demo-user
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python -m pytest backend/tests/test_five_person_interaction.py -v --junitxml="$run_dir/results.xml"
printf 'Isolated simulation evidence: %s\n' "$run_dir"
